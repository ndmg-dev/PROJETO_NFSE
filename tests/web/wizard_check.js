const { JSDOM } = require("jsdom"); const fs = require("fs");
const html = fs.readFileSync(process.argv[2], "utf8");
const esperar = ms => new Promise(r => setTimeout(r, ms));
let falhas = 0;
const conferir = (nome, ok) => { console.log((ok ? "  ✓ " : "  ✗ ") + nome); if (!ok) falhas++; };

async function cenario(nome, { url = "http://localhost/setup", status, resposta = {}, aoPostar }, roteiro) {
  console.log("\n" + nome);
  const dom = new JSDOM(html, { runScripts: "dangerously", url });
  const w = dom.window, d = w.document, chamadas = [];
  w.fetch = async (u, opc = {}) => {
    chamadas.push({ url: String(u), opc });
    if (String(u).endsWith("/setup/status")) return { status: 200, ok: true, json: async () => status };
    if (String(u).endsWith("/setup")) { const r = aoPostar ? aoPostar(opc) : { status: 201 }; return { status: r.status, ok: r.status < 300, json: async () => r.corpo || {} }; }
    throw new Error("url inesperada " + u);
  };
  // o script roda no carregamento, antes do fetch acima existir: recarrega a verificação
  await esperar(50);
  w.eval("verificar()");
  await esperar(80);
  await roteiro({ w, d, chamadas });
}
const visivel = (d, id) => !d.getElementById(id).classList.contains("hidden");
const preencher = (d, v) => { for (const [k, x] of Object.entries(v)) d.getElementById(k).value = x; };
const bom = { escritorio: "Meu Escritório", email: "a@b.com", senha: "uma-senha-longa", senha2: "uma-senha-longa" };
const ok3 = { configurado: false, verificacoes: [
  { id: "banco", rotulo: "Banco de dados", ok: true }, { id: "esquema", rotulo: "Estrutura do banco", ok: true }, { id: "redis", rotulo: "Fila de tarefas", ok: true }] };

(async () => {
  await cenario("1. sistema pronto, código na URL", { url: "http://localhost/setup?codigo=K7QH-2MXP", status: ok3 }, async ({ w, d }) => {
    conferir("formulário aparece", visivel(d, "cardForm"));
    conferir("as 3 verificações listadas", d.querySelectorAll("#listaVerificacoes li").length === 3);
    conferir("código preenchido sozinho", d.getElementById("codigo").value === "K7QH-2MXP");
    conferir("código removido da barra de endereço", w.location.search === "");
    conferir("dica diz que foi recebido", d.getElementById("dicaCodigo").textContent.includes("Recebido"));
  });

  await cenario("2. sem código na URL", { status: ok3 }, async ({ d }) => {
    conferir("campo vazio e dica explica onde achar", d.getElementById("codigo").value === "" && d.getElementById("dicaCodigo").textContent.includes("log"));
  });

  await cenario("3. validação no navegador (nada é enviado)", { status: ok3 }, async ({ d, chamadas }) => {
    for (const [rotulo, mud, trecho] of [
      ["nome curto", { escritorio: "X" }, "nome do escritório"],
      ["e-mail inválido", { email: "isto" }, "e-mail"],
      ["senha curta", { senha: "curta", senha2: "curta" }, "pelo menos 10"],
      ["senhas diferentes", { senha2: "outra-senha-longa" }, "não são iguais"],
      ["sem código", {}, "código"],
    ]) {
      preencher(d, { ...bom, codigo: rotulo === "sem código" ? "" : "AAAA-AAAA", ...mud });
      d.getElementById("btnCriar").click();
      await esperar(20);
      conferir(rotulo + " → mensagem certa", d.getElementById("msgCriar").textContent.toLowerCase().includes(trecho));
    }
    conferir("nenhum POST /setup foi feito", !chamadas.some(c => c.opc.method === "POST"));
  });

  await cenario("4. sucesso", { status: ok3 }, async ({ d, chamadas }) => {
    preencher(d, { ...bom, codigo: "k7qh-2mxp" });
    d.getElementById("btnCriar").click();
    await esperar(80);
    const post = chamadas.find(c => c.opc.method === "POST");
    const corpo = JSON.parse(post.opc.body);
    conferir("enviou os 4 campos certos", corpo.codigo === "k7qh-2mxp" && corpo.escritorio === "Meu Escritório" && corpo.email === "a@b.com" && corpo.senha === "uma-senha-longa");
    conferir("NÃO enviou a confirmação de senha", !("senha2" in corpo));
    conferir("tela de pronto aparece", visivel(d, "cardPronto"));
    conferir("formulário some", !visivel(d, "cardForm"));
    conferir("link para o painel e para /instalar", [...d.querySelectorAll("#cardPronto a")].map(a => a.getAttribute("href")).join() === "/,/instalar");
  });

  for (const [st, trecho] of [[403, "incorreto"], [409, "já foi configurado"], [429, "Aguarde"], [422, "Confira"], [503, "banco de dados"], [500, "erro 500"]]) {
    await cenario("5. servidor responde " + st, { status: ok3, aoPostar: () => ({ status: st }) }, async ({ d }) => {
      preencher(d, { ...bom, codigo: "AAAA-AAAA" });
      d.getElementById("btnCriar").click();
      await esperar(60);
      conferir("mensagem em português: …" + trecho + "…", d.getElementById("msgCriar").textContent.includes(trecho));
      conferir("continua no formulário e o botão volta a funcionar", visivel(d, "cardForm") && !d.getElementById("btnCriar").disabled);
    });
  }

  await cenario("6. banco ainda subindo", { status: { configurado: null, verificacoes: [
      { id: "banco", rotulo: "Banco de dados", ok: false, detalhe: "Não foi possível conectar ao banco de dados." },
      { id: "esquema", rotulo: "Estrutura do banco", ok: false, detalhe: "Aguardando o banco de dados." },
      { id: "redis", rotulo: "Fila de tarefas", ok: true }] } }, async ({ d }) => {
    conferir("formulário NÃO aparece", !visivel(d, "cardForm"));
    conferir("mostra o que falhou", d.getElementById("listaVerificacoes").textContent.includes("Não foi possível conectar"));
    conferir("oferece verificar de novo", visivel(d, "btnVerificar") || !d.getElementById("btnVerificar").classList.contains("hidden"));
  });

  await cenario("7. já configurado", { status: { configurado: true, verificacoes: [] } }, async ({ d }) => {
    conferir("mostra 'já configurado' com link para o painel", visivel(d, "cardJaConfigurado") && d.querySelector("#cardJaConfigurado a").getAttribute("href") === "/");
    conferir("formulário escondido", !visivel(d, "cardForm"));
  });

  await cenario("8. texto hostil vindo do servidor não injeta elementos", { status: { configurado: false, verificacoes: [
      { id: "x", rotulo: '<img src=x id="xss">', ok: false, detalhe: '<b id="xss2">oi</b>' }] } }, async ({ d }) => {
    conferir("nenhum elemento injetado", d.querySelectorAll("#xss, #xss2, #listaVerificacoes img, #listaVerificacoes b").length === 0);
    conferir("aparece como texto literal", d.getElementById("listaVerificacoes").textContent.includes('<img src=x id="xss">'));
  });

  console.log(falhas ? `\n${falhas} FALHA(S)` : "\ntodos os cenários passaram");
  process.exit(falhas ? 1 : 0);
})();
