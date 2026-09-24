// Página /instalar em jsdom: detecção de sistema, endereço exibido e o link.
const { JSDOM } = require("jsdom"); const fs = require("fs");
const html = fs.readFileSync(process.argv[2], "utf8");
let falhas = 0;
const conferir = (nome, ok) => { console.log((ok ? "  ✓ " : "  ✗ ") + nome); if (!ok) falhas++; };

// `userAgent` NÃO é opção do construtor do JSDOM (só do ResourceLoader): passá-lo ali
// é ignorado em silêncio e todo cenário roda com o agente padrão do jsdom. O gancho
// beforeParse troca o valor ANTES de os scripts da página rodarem.
function abrir(url, userAgent) {
  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    url,
    beforeParse(window) {
      Object.defineProperty(window.navigator, "userAgent", { get: () => userAgent });
    },
  });
  return dom.window.document;
}
const WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36";
const MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15";
const LINUX = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36";

console.log("\no harness aplica o agente de usuário de verdade");
for (const [nome, ua] of [["Windows", WINDOWS], ["Mac", MAC], ["Linux", LINUX]]) {
  const w = new JSDOM("", { url: "http://x/", beforeParse(win) { Object.defineProperty(win.navigator, "userAgent", { get: () => ua }); } }).window;
  conferir("navigator.userAgent de " + nome + " chegou à página", w.navigator.userAgent === ua);
}

console.log("\nem um Windows");
let d = abrir("http://10.0.0.106:8000/instalar", WINDOWS);
conferir("não mostra o aviso de outro sistema", d.getElementById("avisoOutroSistema").classList.contains("hidden"));
conferir("mostra o endereço do servidor a que vai se conectar", d.getElementById("endereco").textContent === "http://10.0.0.106:8000");
const a = d.getElementById("baixar");
conferir("o botão aponta para o instalador", a.getAttribute("href") === "/instalar/Instalar-Agente-NFSe.bat");
conferir("o link é de download", a.hasAttribute("download"));

for (const [nome, ua] of [["Mac", MAC], ["Linux", LINUX]]) {
  console.log("\nem um " + nome);
  d = abrir("http://servidor:8000/instalar", ua);
  conferir("mostra o aviso de que só funciona no Windows", !d.getElementById("avisoOutroSistema").classList.contains("hidden"));
  conferir("o botão continua disponível (o aviso não bloqueia)", !!d.getElementById("baixar"));
}

console.log("\nendereço com nome de máquina e porta");
d = abrir("https://nfse.escritorio.local/instalar", WINDOWS);
conferir("mostra https e o nome", d.getElementById("endereco").textContent === "https://nfse.escritorio.local");

console.log("\nsegurança");
conferir("nada da página usa innerHTML", !/innerHTML/.test(html));

console.log(falhas ? `\n${falhas} FALHA(S)` : "\ntodos os cenários passaram");
process.exit(falhas ? 1 : 0);
