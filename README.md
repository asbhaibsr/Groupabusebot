<!-- ======================= AS-FILTER-BOT — Single File ======================= -->
<!-- Save as: index.html  |  Host on GitHub Pages or any static host -->
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>AS-FILTER-BOT • README</title>
  <meta name="description" content="AS-FILTER-BOT • Smart Telegram group moderation with filters, tagging, TicTacToe, whitelist/warn, and 24×7 health." />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet" />
  <style>
    :root{
      --bg: #0b1020; --card:#111834; --text:#e8ecff; --muted:#aab3d1; --accent:#4f80ff; --accent-2:#1e88e5;
      --ok:#23c55e; --warn:#f59e0b; --danger:#ef4444; --shadow: 0 10px 30px rgba(0,0,0,.35);
      --radius: 18px;
    }
    @media (prefers-color-scheme: light) {
      :root{ --bg:#f7f9ff; --card:#ffffff; --text:#1c2440; --muted:#4a5578; --accent:#2b5cff; }
    }
    *{box-sizing:border-box}
    body{
      margin:0; font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;
      background:radial-gradient(1200px 800px at 10% -10%, rgba(79,128,255,.25), transparent 40%),
                 radial-gradient(900px 600px at 110% 20%, rgba(30,136,229,.25), transparent 35%),
                 var(--bg); color:var(--text);
    }
    a{ color:inherit; text-decoration:none }
    .wrap{ max-width:980px; margin:40px auto; padding:0 16px }
    .card{ background:var(--card); border-radius:var(--radius); box-shadow:var(--shadow); padding:24px }
    header{ text-align:center; margin-bottom:22px }
    header img{ width:120px; height:120px; border-radius:50%; object-fit:cover; box-shadow:0 6px 20px rgba(0,0,0,.35) }
    h1{ margin:14px 0 6px; font-size:32px }
    .badges{ display:flex; gap:10px; justify-content:center; flex-wrap:wrap; margin:14px 0 }
    .type-line{ font-size:18px; min-height:28px; opacity:.95 }
    .grid{ display:grid; grid-template-columns:1fr; gap:16px }
    @media (min-width:900px){ .grid{ grid-template-columns: 1fr } }
    .section{ background:var(--card); border-radius:var(--radius); padding:22px; box-shadow:var(--shadow) }
    .section h2{ margin:0 0 14px; font-size:22px }
    .deploy table, .features table, .commands table{ width:100%; border-collapse:separate; border-spacing:0 8px }
    .deploy th, .deploy td, .features th, .features td, .commands th, .commands td{ text-align:left; padding:10px 12px; background:rgba(255,255,255,.02) }
    .deploy th, .features th, .commands th{ background:transparent; color:var(--muted); font-weight:600; padding:0 12px 6px }
    .pill{
      display:inline-flex; align-items:center; gap:8px; padding:10px 14px; border-radius:999px; font-weight:600;
      background:linear-gradient(180deg, rgba(79,128,255,.16), rgba(79,128,255,.06)); border:1px solid rgba(79,128,255,.25)
    }
    .btn{
      display:inline-flex; align-items:center; justify-content:center; gap:8px; padding:10px 14px; border-radius:999px;
      background:var(--accent-2); color:#fff; font-weight:600; border:none; cursor:pointer;
      transition:transform .06s ease, filter .15s ease; white-space:nowrap
    }
    .btn.round{ width:46px; height:46px; border-radius:50% }
    .btn:hover{ filter:brightness(1.05) }
    .btn:active{ transform:translateY(1px) }
    .btn.ghost{ background:transparent; color:var(--accent-2); border:1px solid var(--accent-2) }
    .mini{ font-size:12px; opacity:.9 }
    .kbd{ font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; background:rgba(255,255,255,.06);
          padding:2px 6px; border-radius:6px; }
    .codeblock{ background:rgba(0,0,0,.35); border:1px solid rgba(255,255,255,.1); border-radius:12px; padding:14px; overflow:auto }
    .copy{ display:inline-flex; gap:8px; align-items:center }
    .chip{ display:inline-block; padding:.1rem .5rem; border-radius:8px; background:rgba(255,255,255,.07); font-size:12px; color:var(--muted) }
    .footer{ text-align:center; color:var(--muted); margin:20px 0 8px }
    /* table row rounding */
    .features td:first-child, .commands td:first-child, .deploy td:first-child{ border-top-left-radius:10px; border-bottom-left-radius:10px }
    .features td:last-child, .commands td:last-child, .deploy td:last-child{ border-top-right-radius:10px; border-bottom-right-radius:10px }
    /* inline buttons inside tables */
    table button{ background:#1e88e5; color:#fff; border:none; padding:6px 10px; border-radius:6px; cursor:pointer; font-size:13px }
    table button:hover{ filter:brightness(1.08) }
    /* responsive scroll */
    .scroll-x{ overflow-x:auto }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <header>
        <img src="https://telegra.ph/file/8ddd3c6c3b7a02a0f1f6c.jpg" alt="AS-FILTER-BOT logo" />
        <h1><b>AS-FILTER-BOT</b></h1>
        <div class="badges">
          <a class="pill" href="https://t.me/asbhai_bsr" target="_blank" rel="noopener"><span>📢</span><span>Update Channel</span></a>
          <a class="pill" href="https://t.me/askiangelbot" target="_blank" rel="noopener"><span>🤖</span><span>Support Group</span></a>
          <a class="pill" href="https://github.com/" target="_blank" rel="noopener"><span>⭐</span><span>Star Repo</span></a>
        </div>
        <div class="type-line"><span id="typewriter"></span></div>
      </header>
    </div>

    <!-- 1-CLICK DEPLOY -->
    <section class="section deploy">
      <h2>🔧 1-Click Deploy</h2>
      <div class="scroll-x">
        <table>
          <thead><tr><th>Platform</th><th>Button</th></tr></thead>
          <tbody>
            <tr>
              <td><b>Koyeb</b></td>
              <td>
                <a class="btn"
                   href="https://app.koyeb.com/deploy?type=docker&image=docker.io/library/python:3.11&env[PORT]=8000&env[MONGO_DB_URI]=&env[API_ID]=&env[API_HASH]=&env[TELEGRAM_BOT_TOKEN]=&name=as-filter-bot&run_command=python%20main.py"
                   target="_blank" rel="noopener">Deploy to Koyeb</a>
              </td>
            </tr>
            <tr>
              <td><b>Railway</b></td>
              <td>
                <a class="btn"
                   href="https://railway.app/new/template?template=https%3A%2F%2Fgithub.com%2Fyourname%2Fas-filter-bot&envs=MONGO_DB_URI,API_ID,API_HASH,TELEGRAM_BOT_TOKEN&optionalEnvs=LOG_CHANNEL_ID"
                   target="_blank" rel="noopener">Deploy on Railway</a>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- FEATURES -->
    <section class="section features">
      <h2>📋 Features In Detail</h2>
      <div class="scroll-x">
        <table>
          <thead><tr><th>#</th><th>Feature</th><th>Command / Action</th><th>Description</th></tr></thead>
          <tbody>
            <tr><td>1</td><td><b>Auto Bio-Link Delete</b></td><td>on join / every message</td><td>Removes users whose bio contains any link & warns them</td></tr>
            <tr><td>2</td><td><b>Abuse Word Filter</b></td><td><span class="kbd">/addabuse &lt;word&gt;</span> (admin)</td><td>Adds custom slangs; deletes + warns</td></tr>
            <tr><td>3</td><td><b>Link / Username Filter</b></td><td>auto</td><td>Deletes Telegram links, <span class="kbd">t.me</span>, <span class="kbd">www.</span> etc.</td></tr>
            <tr><td>4</td><td><b>Edited Message Nuker</b></td><td>auto</td><td>Deletes edited messages to stop bypass</td></tr>
            <tr><td>5</td><td><b>Whitelist System</b></td><td><span class="kbd">/free</span>, <span class="kbd">/unfree</span>, <span class="kbd">/freelist</span></td><td>Exclude trusted users</td></tr>
            <tr><td>6</td><td><b>Warn → Mute → Ban</b></td><td>configurable</td><td>Set limits & punishment via buttons</td></tr>
            <tr><td>7</td><td><b>Tagging Suite</b></td><td><span class="kbd">/tagall</span>, <span class="kbd">/onlinetag</span>, <span class="kbd">/admin</span>, <span class="kbd">/tagstop</span></td><td>Tag everyone / online / admins</td></tr>
            <tr><td>8</td><td><b>Tic Tac Toe Game</b></td><td><span class="kbd">/tictac @user1 @user2</span></td><td>Play zero-katta inside group</td></tr>
            <tr><td>9</td><td><b>Lock &amp; Secret Chat</b></td><td><span class="kbd">/lock @user msg</span>, <span class="kbd">/secretchat @user msg</span></td><td>Show message to only one user</td></tr>
            <tr><td>10</td><td><b>Flask Health API</b></td><td><span class="kbd">/</span> (port 8000)</td><td>Uptime monitoring for Koyeb / Render</td></tr>
            <tr><td>11</td><td><b>Broadcast &amp; Stats</b></td><td><span class="kbd">/broadcast</span> (owner) <span class="kbd">/stats</span></td><td>Owner tools</td></tr>
            <tr><td>12</td><td><b>Cleanup Tool</b></td><td><span class="kbd">/cleartempdata</span></td><td>Clear memory & stale DB records</td></tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- INSTALLATION -->
    <section class="section">
      <h2>⚙️ Installation</h2>

      <div class="codeblock">
        <div class="copy">
          <button class="btn" data-copy="git clone https://github.com/yourname/as-filter-bot.git
cd as-filter-bot
pip install -r requirements.txt">Copy</button>
          <span class="mini">Clone &amp; install</span>
        </div>
        <pre><code>git clone https://github.com/yourname/as-filter-bot.git
cd as-filter-bot
pip install -r requirements.txt</code></pre>
      </div>

      <div class="codeblock" style="margin-top:12px">
        <div class="copy">
          <button class="btn" data-copy="cp sample.env .env
nano .env">Copy</button>
          <span class="mini">Environment variables</span>
        </div>
        <pre><code>cp sample.env .env
nano .env</code></pre>
      </div>

      <div class="scroll-x" style="margin-top:10px">
        <table>
          <thead><tr><th>Key</th><th>Sample</th></tr></thead>
          <tbody>
            <tr><td><span class="kbd">API_ID</span></td><td><span class="kbd">123456</span></td></tr>
            <tr><td><span class="kbd">API_HASH</span></td><td><span class="kbd">abcdef123456...</span></td></tr>
            <tr><td><span class="kbd">TELEGRAM_BOT_TOKEN</span></td><td><span class="kbd">123456:ABC-DEF...</span></td></tr>
            <tr><td><span class="kbd">MONGO_DB_URI</span></td><td><span class="kbd">mongodb+srv://user:pass@cluster0.x.mongodb.net/?retryWrites=true&amp;w=majority</span></td></tr>
            <tr><td><span class="kbd">LOG_CHANNEL_ID</span></td><td><span class="kbd">-1002717243409</span></td></tr>
          </tbody>
        </table>
        <p class="mini" style="margin:10px 2px 0">
          Tip: Create bot → <a href="https://t.me/BotFather" target="_blank" rel="noopener">@BotFather</a> • Get API ID / HASH → <a href="https://my.telegram.org" target="_blank" rel="noopener">my.telegram.org</a>
        </p>
      </div>

      <div class="codeblock" style="margin-top:12px">
        <div class="copy">
          <button class="btn" data-copy="python main.py">Copy</button>
          <span class="mini">Run</span>
        </div>
        <pre><code>python main.py</code></pre>
      </div>
    </section>

    <!-- COMMANDS -->
    <section class="section commands">
      <h2>🎛️ Bot Commands (Copy Friendly)</h2>
      <div class="scroll-x">
        <table>
          <thead><tr><th>Command</th><th>Usage</th></tr></thead>
          <tbody>
            <tr><td><b>Start</b></td><td><button data-copy="/start">Copy</button> <span class="kbd">/start</span></td></tr>
            <tr><td><b>Help</b></td><td><button data-copy="/help">Copy</button> <span class="kbd">/help</span></td></tr>
            <tr><td><b>Settings</b></td><td><button data-copy="/settings">Copy</button> <span class="kbd">/settings</span></td></tr>
            <tr><td><b>Whitelist</b></td><td><button data-copy="/free">Copy</button> <span class="kbd">/free</span> (reply)</td></tr>
            <tr><td><b>Un-Whitelist</b></td><td><button data-copy="/unfree">Copy</button> <span class="kbd">/unfree</span> (reply)</td></tr>
            <tr><td><b>Whitelist List</b></td><td><button data-copy="/freelist">Copy</button> <span class="kbd">/freelist</span></td></tr>
            <tr><td><b>Tic Tac Toe</b></td><td><button data-copy="/tictac @user1 @user2">Copy</button> <span class="kbd">/tictac @user1 @user2</span></td></tr>
            <tr><td><b>Lock Message</b></td><td><button data-copy="/lock @username secret message">Copy</button> <span class="kbd">/lock @username secret message</span></td></tr>
            <tr><td><b>Secret Chat</b></td><td><button data-copy="/secretchat @username hi">Copy</button> <span class="kbd">/secretchat @username hi</span></td></tr>
            <tr><td><b>Tag All</b></td><td><button data-copy="/tagall Good morning">Copy</button> <span class="kbd">/tagall Good morning</span></td></tr>
            <tr><td><b>Tag Online</b></td><td><button data-copy="/onlinetag Join fast">Copy</button> <span class="kbd">/onlinetag Join fast</span></td></tr>
            <tr><td><b>Tag Admins</b></td><td><button data-copy="/admin need help">Copy</button> <span class="kbd">/admin need help</span></td></tr>
            <tr><td><b>Stop Tags</b></td><td><button data-copy="/tagstop">Copy</button> <span class="kbd">/tagstop</span></td></tr>
            <tr><td><b>Check Perms</b></td><td><button data-copy="/checkperms">Copy</button> <span class="kbd">/checkperms</span></td></tr>
            <tr><td><b>Add Abuse</b></td><td><button data-copy="/addabuse word">Copy</button> <span class="kbd">/addabuse word</span></td></tr>
            <tr><td><b>Stats</b></td><td><button data-copy="/stats">Copy</button> <span class="kbd">/stats</span> (owner only)</td></tr>
            <tr><td><b>Broadcast</b></td><td><button data-copy="/broadcast">Copy</button> <span class="kbd">/broadcast</span> (owner only)</td></tr>
            <tr><td><b>Clean DB</b></td><td><button data-copy="/cleartempdata">Copy</button> <span class="kbd">/cleartempdata</span> (owner only)</td></tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- CONTACT & SUPPORT -->
    <section class="section">
      <h2>📞 Contact &amp; Support</h2>
      <div class="grid">
        <div>
          <p><span class="chip">Update Channel</span></p>
          <a class="btn" href="https://t.me/asbhai_bsr" target="_blank" rel="noopener">📢 Join</a>
        </div>
        <div>
          <p><span class="chip">Support Group</span></p>
          <a class="btn" href="https://t.me/askiangelbot" target="_blank" rel="noopener">🤖 Get Help</a>
        </div>
        <div>
          <p><span class="chip">Donation (UPI)</span></p>
          <button class="btn" data-copy="arsadsaifi8272@ibl">Copy UPI</button>
          <span class="kbd">arsadsaifi8272@ibl</span>
        </div>
        <div>
          <p><span class="chip">Developer</span></p>
          <a class="btn" href="https://t.me/asprmotion" target="_blank" rel="noopener">💬 DM</a>
        </div>
      </div>
    </section>

    <!-- LICENSE -->
    <section class="section">
      <h2>🪪 License</h2>
      <p>MIT © <a href="https://github.com/asbhai" target="_blank" rel="noopener">AS Bhai</a> – feel free to fork &amp; modify.</p>
    </section>

    <p class="footer mini">
      💡 Heads-up: Browsers require a user gesture for clipboard writes; all “Copy” buttons here run on click. :contentReference[oaicite:1]{index=1}
    </p>
  </div>

  <!-- Typing Animation -->
  <script>
    const phrases = [
      "Smart Group Moderation Bot ✨",
      "Auto Delete Bio-Link / Abuse / Links 🔗",
      "Zero Katte Tic Tac Toe Game 🎮",
      "Tag All / Online / Admins 🎯",
      "Whitelist & Warn System ⚠️",
      "24×7 Flask Health Check 🩺"
    ];
    const el = document.getElementById("typewriter");
    let i = 0, j = 0, dir = 1;
    const type = () => {
      el.textContent = phrases[i].slice(0, j);
      j += dir;
      if (j > phrases[i].length) { dir = -1; setTimeout(type, 850); return; }
      if (j < 0) { dir = 1; i = (i + 1) % phrases.length; setTimeout(type, 300); return; }
      setTimeout(type, 60);
    };
    type();
  </script>

  <!-- Copy-to-Clipboard for all buttons with data-copy -->
  <script>
    const toast = (btn, ok = true) => {
      const original = btn.textContent;
      btn.textContent = ok ? "Copied!" : "Failed";
      btn.style.filter = ok ? "brightness(1.15)" : "grayscale(1)";
      setTimeout(() => { btn.textContent = original; btn.style.filter = ""; }, 900);
    };
    const doCopy = async (text, btn) => {
      try {
        await navigator.clipboard.writeText(text); // requires user gesture (our click) ✔
        toast(btn, true);
      } catch (e) {
        // Fallback: create a temporary textarea
        try {
          const ta = document.createElement("textarea");
          ta.value = text; document.body.appendChild(ta);
          ta.select(); document.execCommand("copy");
          ta.remove(); toast(btn, true);
        } catch { toast(btn, false); }
      }
    };
    document.querySelectorAll("[data-copy]").forEach(btn => {
      btn.addEventListener("click", () => doCopy(btn.getAttribute("data-copy"), btn));
    });
  </script>
</body>
</html>
<!-- ===================== END — AS-FILTER-BOT Single File ===================== -->
