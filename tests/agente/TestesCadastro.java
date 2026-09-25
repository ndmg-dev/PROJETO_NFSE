import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

/** Testes da lógica de CadastroEmpresa (sem JUnit): make test-agente. */
public final class TestesCadastro {
    static int falhas = 0;

    static void confere(String nome, boolean ok) {
        System.out.println((ok ? "  ✓ " : "  ✗ ") + nome);
        if (!ok) falhas++;
    }

    static boolean lanca(Runnable r) {
        try { r.run(); return false; } catch (RuntimeException e) { return true; }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("extração do CNPJ do certificado");
        var real = CadastroEmpresa.extrair(
            "CN=NORDESTINES RESTAURANTE LTDA:24835727000157,OU=videoconferencia,O=ICP-Brasil,C=BR");
        confere("e-CNPJ real: CNPJ e razão social", real.isPresent()
            && real.get().cnpj().equals("24835727000157")
            && real.get().razaoSocial().equals("NORDESTINES RESTAURANTE LTDA"));
        confere("razão social com vírgula escapada (RFC 2253)",
            CadastroEmpresa.extrair("CN=A\\, B LTDA:24835727000157,C=BR").map(d -> d.razaoSocial()).orElse("").equals("A, B LTDA"));
        confere("razão social com dois-pontos", CadastroEmpresa.extrair("CN=EMPRESA: FILIAL LTDA:24835727000157").map(d -> d.razaoSocial()).orElse("").equals("EMPRESA: FILIAL LTDA"));
        confere("e-CPF (11 dígitos) NÃO vira empresa", CadastroEmpresa.extrair("CN=FULANO DE TAL:12345678909,C=BR").isEmpty());
        confere("dígito verificador errado é recusado", CadastroEmpresa.extrair("CN=X LTDA:24835727000158").isEmpty());
        confere("CNPJ com todos os dígitos iguais é recusado", CadastroEmpresa.extrair("CN=X LTDA:11111111111111").isEmpty());
        confere("sem CNPJ no CN", CadastroEmpresa.extrair("CN=SERVIDOR WEB,O=X").isEmpty());
        confere("razão social vazia", CadastroEmpresa.extrair("CN=:24835727000157").isEmpty());
        confere("subject ilegível não estoura", CadastroEmpresa.extrair("isto nao e um DN").isEmpty());
        confere("subject vazio não estoura", CadastroEmpresa.extrair("").isEmpty());
        confere("CNPJ conhecido é válido", CadastroEmpresa.cnpjValido("07199546000162"));

        System.out.println("\nendereço do sistema");
        confere("localhost com porta", !lanca(() -> { try { CadastroEmpresa.baseSegura("http://localhost:8000/"); } catch (Exception e) { throw new RuntimeException(e); } }));
        confere("127.0.0.1", !lanca(() -> { try { CadastroEmpresa.baseSegura("http://127.0.0.1:8000"); } catch (Exception e) { throw new RuntimeException(e); } }));
        for (String ruim : new String[]{"http://10.0.0.5:8000", "https://localhost:8000", "http://localhost.evil.com", "http://localhost@evil.com", "http://evil.com/localhost", "", null}) {
            confere("recusa " + ruim, lanca(() -> { try { CadastroEmpresa.baseSegura(ruim); } catch (Exception e) { throw new RuntimeException(e); } }));
        }

        System.out.println("\nJSON");
        confere("escapa aspas, barra e quebra de linha", CadastroEmpresa.json("a\"b\\c\nd").equals("\"a\\\"b\\\\c\\nd\""));

        System.out.println("\nconversa com o sistema (servidor de mentira em 127.0.0.1)");
        List<String> vistos = new ArrayList<>();
        int[] statusEmpresas = {201};
        HttpServer srv = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        srv.createContext("/auth/login", ex -> {
            String corpo = new String(ex.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
            vistos.add("login " + corpo);
            boolean ok = corpo.contains("\"senha\":\"certa-123\"");
            byte[] r = (ok ? "{\"access_token\":\"TOK\",\"refresh_token\":\"R\"}" : "{\"detail\":\"x\"}").getBytes();
            ex.sendResponseHeaders(ok ? 200 : 401, r.length); ex.getResponseBody().write(r); ex.close();
        });
        srv.createContext("/empresas", ex -> {
            String corpo = new String(ex.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
            vistos.add("empresas " + ex.getRequestHeaders().getFirst("Authorization") + " " + corpo);
            byte[] r = "{\"detail\":\"CNPJ já cadastrado\"}".getBytes(StandardCharsets.UTF_8);
            ex.sendResponseHeaders(statusEmpresas[0], r.length); ex.getResponseBody().write(r); ex.close();
        });
        srv.start();
        String base = "http://127.0.0.1:" + srv.getAddress().getPort();
        try {
            String tok = CadastroEmpresa.entrar(base, "  Ana@Local.com ", "certa-123");
            confere("login devolve o token", tok.equals("TOK"));
            confere("o e-mail vai sem espaços", vistos.get(0).contains("\"email\":\"Ana@Local.com\""));
            boolean recusou = false;
            try { CadastroEmpresa.entrar(base, "a@b.com", "errada-123"); } catch (CadastroEmpresa.ErroDeCadastro e) { recusou = e.getMessage().contains("incorretos"); }
            confere("senha errada -> mensagem clara", recusou);
            var dados = new CadastroEmpresa.Dados("24835727000157", "NORDESTINES RESTAURANTE LTDA");
            confere("201 -> CRIADA", CadastroEmpresa.cadastrar(base, tok, dados) == CadastroEmpresa.Situacao.CRIADA);
            confere("o token e o corpo certos vão para /empresas", vistos.get(vistos.size() - 1).equals(
                "empresas Bearer TOK {\"cnpj\":\"24835727000157\",\"razao_social\":\"NORDESTINES RESTAURANTE LTDA\"}"));
            statusEmpresas[0] = 409;
            confere("409 -> JA_EXISTIA", CadastroEmpresa.cadastrar(base, tok, dados) == CadastroEmpresa.Situacao.JA_EXISTIA);
            statusEmpresas[0] = 500;
            boolean erro = false;
            try { CadastroEmpresa.cadastrar(base, tok, dados); } catch (CadastroEmpresa.ErroDeCadastro e) { erro = e.getMessage().contains("500"); }
            confere("500 vira erro explicado, não sucesso", erro);
        } finally { srv.stop(0); }
        boolean fora = false;
        try { CadastroEmpresa.entrar("http://127.0.0.1:1", "a@b.com", "certa-123"); } catch (CadastroEmpresa.ErroDeCadastro e) { fora = e.getMessage().contains("aberto"); }
        confere("sistema desligado -> pede para abrir o NFS-e", fora);

        System.out.println(falhas == 0 ? "\ntodos os testes passaram" : "\n" + falhas + " FALHA(S)");
        System.exit(falhas == 0 ? 0 : 1);
    }
}
