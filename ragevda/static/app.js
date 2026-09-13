// RAG-EVDA split frontend (was inline JS in webapp.py INDEX_HTML).
(function () {
  function csrf() {
    const m = document.cookie.match(/(?:^|; )csrf=([^;]+)/);
    if (m) return decodeURIComponent(m[1]);
    const t = Math.random().toString(36).slice(2);
    document.cookie = "csrf=" + encodeURIComponent(t) + "; path=/; SameSite=Lax";
    return t;
  }
  async function poll(job) {
    const box = document.getElementById("job"),
      bar = document.getElementById("bar"),
      logs = document.getElementById("logs"),
      out = document.getElementById("outputs");
    while (true) {
      const r = await fetch("/status/" + job);
      const j = await r.json();
      box.textContent = j.status + " · " + (j.stage || "") + " · " + (j.progress || 0) + "%";
      bar.style.width = (j.progress || 0) + "%";
      logs.textContent = (j.logs || []).slice(-80).join("\n");
      if (j.status === "done") {
        out.innerHTML = '<a href="/files/' + job + '/report.json">report.json</a> · ' +
          '<a href="/files/' + job + '/dashboard.html">dashboard.html</a> · ' +
          '<a href="/files/' + job + '/rag_content_brief.md">brief</a> · ' +
          '<a href="/files/' + job + '/llms.txt">llms.txt</a>';
        break;
      }
      if (j.status === "error") { box.textContent = "error: " + j.error; break; }
      await new Promise((r) => setTimeout(r, 2000));
    }
  }
  document.getElementById("audit-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const r = await fetch("/run", {
      method: "POST", body: new URLSearchParams(fd),
      headers: { "X-CSRF-Token": csrf() },
    });
    const j = await r.json();
    if (j.error) { alert(j.error); return; }
    poll(j.job);
  });
})();
