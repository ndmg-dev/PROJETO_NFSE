/**
 * Mesmo spike, com janela em vez de terminal — para quem não quer usar
 * PowerShell. A lógica é a mesma (Nucleo.java); isto é só a apresentação.
 *
 * Como rodar: dê duplo clique em testar.bat na mesma pasta. Ele compila e
 * abre esta janela sozinho.
 */
import java.awt.BorderLayout;
import java.awt.Font;
import java.awt.GridLayout;
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;
import javax.swing.JOptionPane;
import javax.swing.JPasswordField;
import java.security.KeyStore;
import javax.swing.JButton;
import javax.swing.JFrame;
import javax.swing.JPanel;
import javax.swing.JScrollPane;
import javax.swing.JTextArea;
import javax.swing.JTextField;
import javax.swing.SwingUtilities;
import javax.swing.SwingWorker;

public final class ProvarHandshakeMTLSGui extends JFrame {

    private final JTextArea saida = new JTextArea();
    private final JTextField campoUrl = new JTextField("https://client.badssl.com/");
    private final JButton botaoListar = new JButton("1. Ver certificados desta máquina");
    private final JButton botaoTestar = new JButton("2. Testar conexão com um certificado");
    private final JButton botaoCadastrar = new JButton("3. Cadastrar a empresa deste certificado no NFS-e");

    private KeyStore storeAberta;

    public static void main(String[] args) {
        SwingUtilities.invokeLater(() -> new ProvarHandshakeMTLSGui().setVisible(true));
    }

    private ProvarHandshakeMTLSGui() {
        super("Teste de certificado — spike do agente NFS-e");
        setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
        setSize(760, 520);
        setLocationRelativeTo(null);

        saida.setEditable(false);
        saida.setFont(new Font(Font.MONOSPACED, Font.PLAIN, 13));
        escrever("Passo 1: clique em \"Ver certificados desta máquina\".");
        escrever("Isto lê o repositório de certificados do Windows — nada é enviado");
        escrever("para lugar nenhum nesta etapa.");
        escrever("");

        botaoTestar.setEnabled(false);
        botaoListar.addActionListener(e -> listarCertificados());
        botaoCadastrar.addActionListener(e -> cadastrarEmpresa());
        botaoTestar.addActionListener(e -> testarConexao());

        JPanel linhaUrl = new JPanel(new BorderLayout(8, 0));
        linhaUrl.add(new javax.swing.JLabel("Endereço de teste:"), BorderLayout.WEST);
        linhaUrl.add(campoUrl, BorderLayout.CENTER);

        JPanel botoes = new JPanel(new GridLayout(2, 2, 8, 8));
        botoes.add(botaoListar);
        botoes.add(botaoTestar);
        botoes.add(botaoCadastrar);

        JPanel topo = new JPanel(new BorderLayout(0, 8));
        topo.add(linhaUrl, BorderLayout.NORTH);
        topo.add(botoes, BorderLayout.SOUTH);

        setLayout(new BorderLayout(8, 8));
        add(topo, BorderLayout.NORTH);
        add(new JScrollPane(saida), BorderLayout.CENTER);
        ((JPanel) getContentPane()).setBorder(
            javax.swing.BorderFactory.createEmptyBorder(10, 10, 10, 10));
    }

    private void escrever(String linha) {
        saida.append(linha + "\n");
        saida.setCaretPosition(saida.getDocument().getLength());
    }

    private void comBotoesDesligados(Runnable tarefa) {
        botaoListar.setEnabled(false);
        botaoTestar.setEnabled(false);
        botaoCadastrar.setEnabled(false);
        new SwingWorker<Void, Void>() {
            @Override protected Void doInBackground() {
                tarefa.run();
                return null;
            }
            @Override protected void done() {
                botaoListar.setEnabled(true);
                botaoTestar.setEnabled(storeAberta != null);
                botaoCadastrar.setEnabled(true);
            }
        }.execute();
    }

    private void listarCertificados() {
        comBotoesDesligados(() -> {
            escrever("Providers de segurança deste Java:");
            Nucleo.nomesDosProviders().forEach(n -> escrever("  " + n));
            escrever("");

            try {
                storeAberta = Nucleo.abrirStoreDoWindows();
            } catch (Nucleo.SunMscapiAusenteException e) {
                escrever("NÃO FOI POSSÍVEL abrir a store do Windows.");
                escrever("Motivo: " + e.getMessage());
                escrever("Isto é esperado se você não estiver no Windows, ou se o Java");
                escrever("instalado não for uma build Windows.");
                return;
            } catch (Exception e) {
                escrever("Erro inesperado ao abrir a store: " + e);
                return;
            }

            try {
                var certificados = Nucleo.listarCertificados(storeAberta);
                if (certificados.isEmpty()) {
                    escrever("Nenhum certificado encontrado em Pessoal (CurrentUser\\My).");
                    escrever("Confira no certmgr.msc se o certificado da empresa aparece ali.");
                    return;
                }
                escrever("Certificados encontrados (" + certificados.size() + "):");
                int i = 0;
                for (var c : certificados) {
                    i++;
                    escrever("  [" + i + "] " + c.subject());
                    escrever("      válido de " + c.validoDe() + " até " + c.validoAte()
                        + (c.vencido() ? "  <<< VENCIDO" : ""));
                }
                escrever("");
                escrever("Passo 2: clique em \"Testar conexão com um certificado\".");
            } catch (Exception e) {
                escrever("Erro ao listar certificados: " + e);
            }
        });
    }

    /** Endereço do sistema local: servidor.txt (escrito pelo instalador) ou a porta padrão. */
    private static String enderecoDoSistema() {
        try {
            String t = java.nio.file.Files.readString(java.nio.file.Path.of("servidor.txt")).trim();
            if (!t.isEmpty()) {
                return t;
            }
        } catch (java.io.IOException e) {
            // sem arquivo: usa o padrão
        }
        return "http://localhost:8000";
    }

    /** Os diálogos precisam rodar na thread da tela; o trabalho de rede roda fora dela. */
    private static <T> T naTela(Supplier<T> pedido) {
        Object[] caixa = new Object[1];
        try {
            SwingUtilities.invokeAndWait(() -> caixa[0] = pedido.get());
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
        @SuppressWarnings("unchecked") T r = (T) caixa[0];
        return r;
    }

    private void cadastrarEmpresa() {
        comBotoesDesligados(() -> {
            escrever("");
            escrever("Cadastrar a empresa do certificado no NFS-e");
            try {
                if (storeAberta == null) {
                    storeAberta = Nucleo.abrirStoreDoWindows();
                }
                List<CadastroEmpresa.Dados> empresas = new ArrayList<>();
                List<String> rotulos = new ArrayList<>();
                for (var c : Nucleo.listarCertificados(storeAberta)) {
                    var dados = CadastroEmpresa.extrair(c.subject());
                    if (dados.isPresent()) {
                        empresas.add(dados.get());
                        rotulos.add(dados.get().razaoSocial() + "  (" + dados.get().cnpj() + ")"
                            + (c.vencido() ? "  [VENCIDO]" : ""));
                    } else {
                        escrever("  ignorado (não é e-CNPJ no padrão ICP-Brasil): " + c.subject());
                    }
                }
                if (empresas.isEmpty()) {
                    escrever("Nenhum e-CNPJ encontrado em Pessoal (CurrentUser\\My). Nada foi cadastrado.");
                    return;
                }
                int escolhida = 0;
                if (empresas.size() > 1) {
                    Object o = naTela(() -> JOptionPane.showInputDialog(this, "Qual empresa cadastrar?",
                        "NFS-e", JOptionPane.QUESTION_MESSAGE, null, rotulos.toArray(), rotulos.get(0)));
                    if (o == null) {
                        escrever("Cancelado.");
                        return;
                    }
                    escolhida = rotulos.indexOf(o);
                }
                var empresa = empresas.get(escolhida);

                var campoEmail = new JTextField(24);
                var campoSenha = new JPasswordField(24);
                int ok = naTela(() -> JOptionPane.showConfirmDialog(this,
                    new Object[]{"Entre com o seu usuário do sistema NFS-e:", "E-mail", campoEmail, "Senha", campoSenha},
                    "Cadastrar " + empresa.razaoSocial(), JOptionPane.OK_CANCEL_OPTION));
                if (ok != JOptionPane.OK_OPTION) {
                    escrever("Cancelado.");
                    return;
                }
                char[] senha = campoSenha.getPassword();
                try {
                    String token = CadastroEmpresa.entrar(enderecoDoSistema(), campoEmail.getText(), new String(senha));
                    var situacao = CadastroEmpresa.cadastrar(enderecoDoSistema(), token, empresa);
                    escrever(situacao == CadastroEmpresa.Situacao.CRIADA
                        ? "CADASTRADA: " + empresa.razaoSocial() + " (" + empresa.cnpj() + "). Atualize a página do NFS-e."
                        : "Esta empresa já estava cadastrada (" + empresa.cnpj() + "). Nada foi alterado.");
                } finally {
                    java.util.Arrays.fill(senha, '\0');
                    campoSenha.setText("");
                }
            } catch (CadastroEmpresa.ErroDeCadastro e) {
                escrever("NÃO CADASTRADA: " + e.getMessage());
            } catch (Nucleo.SunMscapiAusenteException e) {
                escrever("NÃO FOI POSSÍVEL abrir a store do Windows: " + e.getMessage());
            } catch (Exception e) {
                escrever("Erro inesperado: " + e);
            }
        });
    }

    private void testarConexao() {
        String url = campoUrl.getText().trim();
        comBotoesDesligados(() -> {
            escrever("");
            escrever("Testando conexão em " + url + " ...");
            try {
                if (storeAberta == null || Nucleo.listarCertificados(storeAberta).isEmpty()) {
                    escrever("NADA FOI TESTADO: não há certificado em Pessoal (CurrentUser\\My).");
                    escrever("Instale o certificado A1 neste Windows e clique em \"1. Ver certificados\".");
                    return;
                }
                var resposta = Nucleo.provarHandshake(storeAberta, url);
                escrever("Resposta HTTP " + resposta.statusCode());
                escrever("A conexão TLS foi concluída e o Java teve acesso ao(s) certificado(s)");
                escrever("sem que a chave privada saísse do Windows.");
                escrever("ATENÇÃO: só é PROVA de que o certificado foi aceito se o servidor exigir");
                escrever("certificado de cliente (o endereço real do ADN). Em um site comum, como");
                escrever("badssl.com, a conexão funciona com ou sem certificado.");
            } catch (Exception e) {
                escrever("A conexão falhou: " + e);
                escrever("Se a mensagem falar de rede/proxy, pode ser bloqueio de firewall,");
                escrever("não um problema do certificado.");
            }
        });
    }
}
