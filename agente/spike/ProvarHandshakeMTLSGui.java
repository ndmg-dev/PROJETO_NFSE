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
        botaoTestar.addActionListener(e -> testarConexao());

        JPanel linhaUrl = new JPanel(new BorderLayout(8, 0));
        linhaUrl.add(new javax.swing.JLabel("Endereço de teste:"), BorderLayout.WEST);
        linhaUrl.add(campoUrl, BorderLayout.CENTER);

        JPanel botoes = new JPanel(new GridLayout(1, 2, 8, 0));
        botoes.add(botaoListar);
        botoes.add(botaoTestar);

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
        new SwingWorker<Void, Void>() {
            @Override protected Void doInBackground() {
                tarefa.run();
                return null;
            }
            @Override protected void done() {
                botaoListar.setEnabled(true);
                botaoTestar.setEnabled(storeAberta != null);
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
