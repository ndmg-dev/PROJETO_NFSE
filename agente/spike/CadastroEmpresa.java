/**
 * Lê CNPJ e razão social de um certificado e-CNPJ (ICP-Brasil) e cadastra a empresa
 * no sistema NFS-e LOCAL. Só lógica: a janela fica em ProvarHandshakeMTLSGui.
 *
 * O CNPJ vem do CN do titular, na convenção da ICP-Brasil "RAZAO SOCIAL:14 dígitos"
 * (visto num certificado real: CN=NORDESTINES RESTAURANTE LTDA:24835727000157). O dígito
 * verificador é conferido; certificado sem esse padrão (e-CPF, outro emissor) NÃO é
 * cadastrado, em vez de adivinhar um CNPJ.
 *
 * Só lê o certificado PÚBLICO. A chave privada nunca é tocada. A senha do sistema é
 * enviada só para o endereço do próprio computador (localhost/127.0.0.1).
 */
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

final class CadastroEmpresa {

    record Dados(String cnpj, String razaoSocial) {}

    enum Situacao { CRIADA, JA_EXISTIA }

    static final class ErroDeCadastro extends Exception {
        ErroDeCadastro(String mensagem) {
            super(mensagem);
        }
    }

    private static final Pattern CN_COM_CNPJ = Pattern.compile("^(.+):(\\d{14})$");
    private static final Pattern TOKEN = Pattern.compile("\"access_token\"\\s*:\\s*\"([^\"]+)\"");
    private static final Pattern DETALHE = Pattern.compile("\"detail\"\\s*:\\s*\"([^\"]*)\"");

    /** @param subject nome do titular (X500Principal.getName(), RFC 2253). */
    static Optional<Dados> extrair(String subject) {
        try {
            for (Rdn rdn : new LdapName(subject).getRdns()) {
                if (!"CN".equalsIgnoreCase(rdn.getType())) {
                    continue;
                }
                Matcher m = CN_COM_CNPJ.matcher(String.valueOf(rdn.getValue()).trim());
                if (m.matches() && cnpjValido(m.group(2)) && !m.group(1).isBlank()) {
                    return Optional.of(new Dados(m.group(2), m.group(1).trim()));
                }
            }
        } catch (javax.naming.InvalidNameException e) {
            // subject ilegível: não é um e-CNPJ que a gente saiba ler
        }
        return Optional.empty();
    }

    static boolean cnpjValido(String cnpj) {
        if (cnpj == null || !cnpj.matches("\\d{14}") || cnpj.chars().distinct().count() == 1) {
            return false;
        }
        return digito(cnpj, 12) == cnpj.charAt(12) - '0' && digito(cnpj, 13) == cnpj.charAt(13) - '0';
    }

    private static int digito(String cnpj, int tamanho) {
        int soma = 0;
        int peso = tamanho - 7;
        for (int i = 0; i < tamanho; i++) {
            soma += (cnpj.charAt(i) - '0') * peso--;
            if (peso < 2) {
                peso = 9;
            }
        }
        int resto = soma % 11;
        return resto < 2 ? 0 : 11 - resto;
    }

    /** Só o próprio computador: a senha do sistema não deve sair dele. */
    static String baseSegura(String url) throws ErroDeCadastro {
        String limpa = url == null ? "" : url.trim().replaceAll("/+$", "");
        if (!limpa.matches("^http://(localhost|127\\.0\\.0\\.1)(:\\d{1,5})?$")) {
            throw new ErroDeCadastro(
                "Por segurança, o cadastro só fala com o sistema neste computador (localhost). "
                    + "Endereço lido: " + (limpa.isEmpty() ? "(vazio)" : limpa));
        }
        return limpa;
    }

    static String json(String texto) {
        StringBuilder sb = new StringBuilder("\"");
        for (char c : texto.toCharArray()) {
            switch (c) {
                case '"' -> sb.append("\\\"");
                case '\\' -> sb.append("\\\\");
                case '\n' -> sb.append("\\n");
                case '\r' -> sb.append("\\r");
                case '\t' -> sb.append("\\t");
                default -> {
                    if (c < 0x20) {
                        sb.append(String.format("\\u%04x", (int) c));
                    } else {
                        sb.append(c);
                    }
                }
            }
        }
        return sb.append('"').toString();
    }

    private static HttpResponse<String> enviar(HttpRequest.Builder b, String corpo) throws ErroDeCadastro {
        try {
            HttpClient cliente = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build();
            return cliente.send(
                b.timeout(Duration.ofSeconds(20)).header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(corpo)).build(),
                HttpResponse.BodyHandlers.ofString());
        } catch (java.io.IOException e) {
            throw new ErroDeCadastro(
                "Não consegui falar com o sistema NFS-e. Ele está aberto? (abra o atalho \"NFS-e\")");
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new ErroDeCadastro("Operação interrompida.");
        }
    }

    private static String detalhe(String corpo) {
        Matcher m = DETALHE.matcher(corpo == null ? "" : corpo);
        return m.find() ? m.group(1) : "";
    }

    static String entrar(String base, String email, String senha) throws ErroDeCadastro {
        HttpResponse<String> r = enviar(
            HttpRequest.newBuilder(URI.create(baseSegura(base) + "/auth/login")),
            "{\"email\":" + json(email.trim()) + ",\"senha\":" + json(senha) + "}");
        if (r.statusCode() == 401) {
            throw new ErroDeCadastro("E-mail ou senha do sistema incorretos.");
        }
        Matcher m = TOKEN.matcher(r.body());
        if (r.statusCode() != 200 || !m.find()) {
            throw new ErroDeCadastro("Não foi possível entrar (HTTP " + r.statusCode() + ").");
        }
        return m.group(1);
    }

    static Situacao cadastrar(String base, String token, Dados d) throws ErroDeCadastro {
        HttpResponse<String> r = enviar(
            HttpRequest.newBuilder(URI.create(baseSegura(base) + "/empresas"))
                .header("Authorization", "Bearer " + token),
            "{\"cnpj\":" + json(d.cnpj()) + ",\"razao_social\":" + json(d.razaoSocial()) + "}");
        return switch (r.statusCode()) {
            case 201 -> Situacao.CRIADA;
            case 409 -> Situacao.JA_EXISTIA;
            case 401, 403 -> throw new ErroDeCadastro("Este usuário não pode cadastrar empresas.");
            default -> throw new ErroDeCadastro(
                "O sistema recusou o cadastro (HTTP " + r.statusCode() + ") " + detalhe(r.body()));
        };
    }

    private CadastroEmpresa() {}
}
