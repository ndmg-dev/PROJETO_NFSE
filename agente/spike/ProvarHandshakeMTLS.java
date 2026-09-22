/**
 * Spike isolado, versão console: prova (ou não) que o handshake mTLS
 * funciona usando um certificado da store do Windows via SunMSCAPI, sem
 * nunca extrair a chave privada para fora da CryptoAPI.
 *
 * Para quem prefere uma janela em vez de terminal, ver ProvarHandshakeMTLSGui
 * — mesma lógica, em Nucleo.java.
 *
 * ESTADO: NÃO EXECUTADO contra um certificado real. Este ambiente é Linux; o
 * provider SunMSCAPI só existe em builds Windows do JDK.
 *
 * Como compilar e rodar (no Windows, com JDK 21+ instalado):
 *   javac *.java
 *   java ProvarHandshakeMTLS
 *
 * Sem argumento, tenta https://client.badssl.com/ — endpoint público que
 * exige certificado de cliente, só para provar que o handshake ocorre (não
 * valida qual certificado). Para testar outro endpoint:
 *   java ProvarHandshakeMTLS https://...
 */
import java.security.KeyStore;
import java.security.cert.X509Certificate;
import java.util.List;

public final class ProvarHandshakeMTLS {

    public static void main(String[] args) throws Exception {
        System.out.println("=== Providers de segurança disponíveis neste JDK ===");
        Nucleo.nomesDosProviders().forEach(n -> System.out.println("  " + n));
        System.out.println();

        System.out.println("=== Abrindo a store do Windows (Windows-MY / SunMSCAPI) ===");
        KeyStore store;
        try {
            store = Nucleo.abrirStoreDoWindows();
        } catch (Nucleo.SunMscapiAusenteException e) {
            System.out.println("FALHOU: " + e.getMessage());
            System.out.println("Esperado em Linux/macOS — só existe em builds Windows.");
            System.out.println("Rode este spike numa estação Windows de verdade.");
            return;
        }

        System.out.println("=== Certificados encontrados ===");
        List<Nucleo.InfoCertificado> certificados = Nucleo.listarCertificados(store);
        if (certificados.isEmpty()) {
            System.out.println("  (nenhum certificado em CurrentUser\\My)");
            return;
        }
        int i = 0;
        for (Nucleo.InfoCertificado c : certificados) {
            i++;
            System.out.printf("  [%d] alias=%s%n      subject=%s%n      validade: %s a %s%s%n",
                i, c.alias(), c.subject(), c.validoDe(), c.validoAte(),
                c.vencido() ? "  <<< VENCIDO" : "");
        }
        System.out.println();

        String url = args.length > 0 ? args[0] : "https://client.badssl.com/";
        System.out.println("=== Handshake mTLS ===");
        System.out.println("GET " + url);
        var resposta = Nucleo.provarHandshake(store, url);
        System.out.println("HTTP " + resposta.statusCode());
        System.out.println(
            "Handshake concluído: a chave privada nunca saiu da CryptoAPI do Windows.");
    }

    private ProvarHandshakeMTLS() {}
}
