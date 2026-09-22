/**
 * Lógica compartilhada entre a versão console (ProvarHandshakeMTLS) e a
 * versão com janela (ProvarHandshakeMTLSGui) do spike. Sem isto, os dois
 * front-ends acabariam com a mesma lógica de CryptoAPI copiada duas vezes.
 */
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.security.KeyStore;
import java.security.NoSuchProviderException;
import java.security.Provider;
import java.security.Security;
import java.security.cert.X509Certificate;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.List;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;

final class Nucleo {

    /** Um certificado encontrado na store, só com o que o spike precisa mostrar. */
    record InfoCertificado(String alias, String subject, Instant validoDe, Instant validoAte) {
        boolean vencido() {
            return Instant.now().isAfter(validoAte);
        }
    }

    static List<String> nomesDosProviders() {
        List<String> nomes = new ArrayList<>();
        for (Provider p : Security.getProviders()) {
            nomes.add(p.getName() + " " + p.getVersionStr());
        }
        return nomes;
    }

    /**
     * Abre a store do Windows. Levanta {@link SunMscapiAusenteException} com
     * mensagem já traduzida quando o provider não existe — é o caso esperado
     * em Linux/macOS, e o único que os front-ends precisam tratar como "não é
     * bug, é ambiente errado".
     */
    static KeyStore abrirStoreDoWindows() throws Exception {
        try {
            KeyStore ks = KeyStore.getInstance("Windows-MY", "SunMSCAPI");
            ks.load(null, null); // SunMSCAPI ignora esses argumentos
            return ks;
        } catch (NoSuchProviderException e) {
            throw new SunMscapiAusenteException(e);
        }
    }

    static final class SunMscapiAusenteException extends Exception {
        SunMscapiAusenteException(Throwable causa) {
            super("Provider SunMSCAPI ausente neste JDK.", causa);
        }
    }

    static List<InfoCertificado> listarCertificados(KeyStore ks) throws Exception {
        List<InfoCertificado> resultado = new ArrayList<>();
        Enumeration<String> aliases = ks.aliases();
        while (aliases.hasMoreElements()) {
            String alias = aliases.nextElement();
            X509Certificate cert = (X509Certificate) ks.getCertificate(alias);
            resultado.add(new InfoCertificado(
                alias,
                cert.getSubjectX500Principal().getName(),
                cert.getNotBefore().toInstant(),
                cert.getNotAfter().toInstant()
            ));
        }
        return resultado;
    }

    /**
     * Faz um GET com o certificado da store apresentado como cliente TLS.
     *
     * Não escolhe um alias específico — a store inteira vai para o
     * KeyManagerFactory, e é o handshake que decide qual certificado
     * apresentar, conforme o que o servidor aceitar. Selecionar um único
     * certificado por CNPJ é trabalho do agente completo, não deste spike.
     */
    static HttpResponse<String> provarHandshake(KeyStore ks, String url) throws Exception {
        KeyManagerFactory kmf =
                KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm());
        // Sem senha: a chave nunca sai da CryptoAPI, então não há segredo
        // para o Java decifrar — é exatamente o ponto deste desenho.
        kmf.init(ks, null);

        SSLContext contexto = SSLContext.getInstance("TLS");
        contexto.init(kmf.getKeyManagers(), null, null);

        HttpClient cliente = HttpClient.newBuilder().sslContext(contexto).build();
        HttpRequest requisicao = HttpRequest.newBuilder(URI.create(url)).GET().build();
        return cliente.send(requisicao, HttpResponse.BodyHandlers.ofString());
    }

    private Nucleo() {}
}
