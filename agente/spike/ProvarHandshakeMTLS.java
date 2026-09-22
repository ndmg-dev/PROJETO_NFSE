/**
 * Spike isolado: prova (ou não) que o handshake mTLS funciona usando um
 * certificado da store do Windows via SunMSCAPI, sem nunca extrair a chave
 * privada para fora da CryptoAPI.
 *
 * Não é o agente. É a mesma lógica da Fase 0 do projeto (poc/fase0_dfe.py):
 * um programa isolado, sem framework, cujo único objetivo é responder uma
 * pergunta binária antes de investir no resto — aqui, "SunMSCAPI consegue
 * fechar um handshake TLS de cliente nesta máquina, com este JDK?".
 *
 * ESTADO: NÃO EXECUTADO. Este ambiente é Linux; o provider SunMSCAPI só
 * existe em builds Windows do JDK. O código compila aqui (javac já foi
 * conferido), mas a prova real só acontece rodando na estação de um
 * contador, com um certificado A1 de verdade na store.
 *
 * Como compilar e rodar (no Windows, com JDK 21+ instalado):
 *   javac ProvarHandshakeMTLS.java
 *   java ProvarHandshakeMTLS
 *
 * Sem argumento, tenta https://client.badssl.com/ — um endpoint público que
 * exige certificado de cliente. Não valida QUAL certificado (isso é dos
 * mantenedores do badssl.com); serve só para provar que o handshake ocorre.
 * Para testar contra outro endpoint: `java ProvarHandshakeMTLS https://...`.
 *
 * O que este spike NÃO faz, de propósito: não escolhe certificado por CNPJ,
 * não fala com a API central, não decide protocolo agente-servidor. Isso é
 * a etapa "agente completo", depois deste spike responder a pergunta.
 */
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.security.KeyStore;
import java.security.KeyStoreException;
import java.security.NoSuchProviderException;
import java.security.Provider;
import java.security.Security;
import java.security.cert.X509Certificate;
import java.util.Enumeration;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;

public final class ProvarHandshakeMTLS {

    public static void main(String[] args) throws Exception {
        imprimirProviders();

        KeyStore store = abrirStoreDoWindows();
        if (store == null) {
            return; // motivo já impresso em abrirStoreDoWindows()
        }

        String aliasEscolhido = listarCertificados(store);
        if (aliasEscolhido == null) {
            System.out.println("(nenhum certificado em CurrentUser\\My — nada para testar)");
            return;
        }

        provarHandshake(store, args.length > 0 ? args[0] : "https://client.badssl.com/");
    }

    private static void imprimirProviders() {
        System.out.println("=== Providers de segurança disponíveis neste JDK ===");
        for (Provider p : Security.getProviders()) {
            System.out.println("  " + p.getName() + " " + p.getVersionStr());
        }
        System.out.println();
    }

    private static KeyStore abrirStoreDoWindows() {
        System.out.println("=== Abrindo a store do Windows (Windows-MY / SunMSCAPI) ===");
        try {
            KeyStore ks = KeyStore.getInstance("Windows-MY", "SunMSCAPI");
            ks.load(null, null); // SunMSCAPI ignora esses argumentos
            return ks;
        } catch (NoSuchProviderException e) {
            System.out.println("FALHOU: provider SunMSCAPI ausente neste JDK.");
            System.out.println("Esperado em Linux/macOS — só existe em builds Windows.");
            System.out.println("Rode este spike numa estação Windows de verdade.");
            return null;
        } catch (KeyStoreException | java.io.IOException
                | java.security.NoSuchAlgorithmException
                | java.security.cert.CertificateException e) {
            System.out.println("FALHOU ao abrir a store: " + e);
            return null;
        }
    }

    private static String listarCertificados(KeyStore ks) throws Exception {
        System.out.println("=== Certificados encontrados ===");
        Enumeration<String> aliases = ks.aliases();
        String primeiro = null;
        int total = 0;
        while (aliases.hasMoreElements()) {
            String alias = aliases.nextElement();
            total++;
            X509Certificate cert = (X509Certificate) ks.getCertificate(alias);
            System.out.printf(
                "  [%d] alias=%s%n      subject=%s%n      validade: %s a %s%n",
                total, alias, cert.getSubjectX500Principal().getName(),
                cert.getNotBefore(), cert.getNotAfter());
            // Seleção aqui é só "o primeiro que aparecer". O agente completo
            // casa pelo CNPJ raiz no subject — não é o que este spike prova.
            if (primeiro == null) {
                primeiro = alias;
            }
        }
        System.out.println();
        return primeiro;
    }

    private static void provarHandshake(KeyStore ks, String url) throws Exception {
        System.out.println("=== Handshake mTLS ===");
        KeyManagerFactory kmf =
                KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm());
        // Sem senha: a chave nunca sai da CryptoAPI, então não há segredo
        // para o Java decifrar — é exatamente o ponto deste desenho.
        kmf.init(ks, null);

        SSLContext contexto = SSLContext.getInstance("TLS");
        contexto.init(kmf.getKeyManagers(), null, null);

        HttpClient cliente = HttpClient.newBuilder().sslContext(contexto).build();
        System.out.println("GET " + url);
        HttpRequest requisicao = HttpRequest.newBuilder(URI.create(url)).GET().build();
        HttpResponse<String> resposta =
                cliente.send(requisicao, HttpResponse.BodyHandlers.ofString());

        System.out.println("HTTP " + resposta.statusCode());
        System.out.println(
            "Handshake concluído: a chave privada nunca saiu da CryptoAPI do Windows.");
    }

    private ProvarHandshakeMTLS() {}
}
