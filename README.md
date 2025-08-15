<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Group Guardian Bot — README</title>
<style>
  :root{
    --bg:#0b0f14;--card:#0f1620;--soft:#121a26;--text:#e6edf3;--muted:#9fb3c8;
    --acc:#5b9cff;--acc2:#6cffc7;--danger:#ff6b6b;--ok:#7ddc6b;--warn:#ffd166;
    --border:#1e2a3a;--code:#0c1117
  }
  *{box-sizing:border-box}
  body{margin:0;background:linear-gradient(180deg,var(--bg),#070a0e);color:var(--text);
       font:16px/1.6 system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,"Helvetica Neue",Arial}
  a{color:var(--acc);text-decoration:none}
  a:hover{opacity:.9}
  .wrap{max-width:980px;margin:48px auto;padding:0 20px}
  .hero{display:flex;gap:20px;align-items:center;justify-content:space-between;flex-wrap:wrap}
  .brand{display:flex;align-items:center;gap:16px}
  .logo{width:56px;height:56px;border-radius:16px;background:linear-gradient(135deg,var(--acc),var(--acc2));
        display:grid;place-items:center;color:#09111a;font-weight:800;box-shadow:0 10px 40px rgba(91,156,255,.25)}
  h1{margin:0;font-size:32px}
  .pill{display:inline-block;padding:6px 10px;border:1px solid var(--border);border-radius:999px;color:var(--muted);
        background:var(--soft);font-size:12px}
  .grid{display:grid;gap:16px}
  .grid-2{grid-template-columns:repeat(2,minmax(0,1fr))}
  @media (max-width:800px){.grid-2{grid-template-columns:1fr}}
  .card{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:18px}
  .card h2{margin:.2rem 0 0.6rem;font-size:20px}
  .muted{color:var(--muted)}
  code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
  pre{background:var(--code);border:1px solid var(--border);border-radius:14px;padding:14px;overflow:auto}
  .kbd{background:#0f1720;border:1px solid var(--border);border-radius:8px;padding:2px 6px}
  table{width:100%;border-collapse:separate;border-spacing:0;overflow:hidden;border-radius:14px;border:1px solid var(--border)}
  th,td{padding:10px 12px;border-bottom:1px solid var(--border);vertical-align:top}
  th{background:#111a25;text-align:left}
  tr:last-child td{border-bottom:none}
  .btnrow{display:flex;gap:10px;flex-wrap:wrap}
  .btn{display:inline-flex;align-items:center;gap:8px;padding:10px 14px;border-radius:12px;
       background:var(--soft);border:1px solid var(--border);color:var(--text)}
  .btn svg{width:18px;height:18px}
  .ok{border-color:#264a33}
  .warn{border-color:#4a3d26}
  .danger{border-color:#4a2626}
  .tag{display:inline-block;padding:4px 8px;border:1px solid var(--border);border-radius:999px;background:var(--soft);color:var(--muted);font-size:12px}
  .footer{margin:28px 0 8px;color:var(--muted);text-align:center}
</style>
</head>
<body>
  <div class="wrap">

    <header class="hero card" style="padding:20px">
      <div class="brand">
        <div class="logo">GG</div>
        <div>
          <h1>Group Guardian Bot</h1>
          <div class="muted">Telegram group moderation bot — abuse/link filter, warn→mute→ban, tagging, games & more.</div>
        </div>
      </div>
      <div class="badges">
        <span class="pill">Python 3.11+</span>
        <span class="pill">Pyrogram</span>
        <span class="pill">MongoDB</span>
        <span class="pill">Koyeb Ready</span>
      </div>
    </header>

    <section class="card">
      <h2>✨ Features</h2>
      <table>
        <thead>
          <tr><th>#</th><th>Feature</th><th>Command / Action</th><th>Description</th></tr>
        </thead>
        <tbody>
          <tr><td>1</td><td>Auto Bio-Link Delete</td><td>On join / every message</td><td>Users whose bio contains links are auto-removed.</td></tr>
          <tr><td>2</td><td>Abuse Word Filter</td><td><span class="kbd">/addabuse &lt;word&gt;</span></td><td>Deletes abusive words + warns user.</td></tr>
          <tr><td>3</td><td>Link / Username Filter</td><td>Automatic</td><td>Blocks <code>t.me</code>, <code>http(s)://</code>, and usernames.</td></tr>
          <tr><td>4</td><td>Edited Message Nuker</td><td>Automatic</td><td>Deletes edited messages to prevent bypass.</td></tr>
          <tr><td>5</td><td>Whitelist System</td><td><span class="kbd">/free</span>, <span class="kbd">/unfree</span>, <span class="kbd">/freelist</span></td><td>Trusted members excluded from filters.</td></tr>
          <tr><td>6</td><td>Warn → Mute → Ban</td><td>Configurable</td><td>Escalating punishments after limits.</td></tr>
          <tr><td>7</td><td>Tagging Suite</td><td><span class="kbd">/tagall</span>, <span class="kbd">/onlinetag</span>, <span class="kbd">/admin</span>, <span class="kbd">/tagstop</span></td><td>Mention everyone / online / admins.</td></tr>
          <tr><td>8</td><td>Tic Tac Toe</td><td><span class="kbd">/tictac @user1 @user2</span></td><td>Play inside the group.</td></tr>
          <tr><td>9</td><td>Lock &amp; Secret Chat</td><td><span class="kbd">/lock @user msg</span>, <span class="kbd">/secretchat @user msg</span></td><td>Private-like messaging in group.</td></tr>
          <tr><td>10</td><td>Flask Health API</td><td><code>GET /</code> (port 8000)</td><td>Uptime monitoring for hosts.</td></tr>
          <tr><td>11</td><td>Broadcast &amp; Stats</td><td><span class="kbd">/broadcast</span>, <span class="kbd">/stats</span> (owner)</td><td>Owner utilities.</td></tr>
          <tr><td>12</td><td>Cleanup Tool</td><td><span class="kbd">/cleartempdata</span></td><td>Clear old temp data.</td></tr>
        </tbody>
      </table>
    </section>

    <section class="grid grid-2">
      <div class="card">
        <h2>🚀 1-Click Deploy</h2>
        <div class="btnrow" style="margin:8px 0 14px">
          <a class="btn" href="https://app.koyeb.com/deploy?type=docker&image=docker.io/library/python:3.11&env[PORT]=8000&env[MONGO_DB_URI]=&env[API_ID]=&env[API_HASH]=&env[TELEGRAM_BOT_TOKEN]=&name=group-guardian-bot&run_command=python%20main.py" target="_blank" rel="noopener">
            <!-- Koyeb icon -->
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12.9 2.1 22 11.2l-4.2 4.2-9.1-9.1zM2 12.1l4.2-4.2 9.1 9.1-4.2 4.2z"/></svg>
            Deploy to Koyeb
          </a>
          <a class="btn" href="https://railway.app/new/template?template=https%3A%2F%2Fgithub.com%2Fyourname%2Fgroup-guardian-bot&envs=MONGO_DB_URI,API_ID,API_HASH,TELEGRAM_BOT_TOKEN&optionalEnvs=LOG_CHANNEL_ID" target="_blank" rel="noopener">
            <!-- Railway icon -->
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M3 4h18v3H3zm0 6h18v3H3zm0 6h18v3H3z"/></svg>
            Deploy on Railway
          </a>
        </div>
        <div class="muted">Set required env vars during deploy. Health check runs on <code>PORT=8000</code>.</div>
      </div>

      <div class="card">
        <h2>⚙️ Local Setup</h2>
        <ol>
          <li>Clone &amp; Install:</li>
        </ol>
        <pre><code>git clone https://github.com/yourname/group-guardian-bot.git
cd group-guardian-bot
pip install -r requirements.txt</code></pre>
        <ol start="2">
          <li>Create <code>.env</code>:</li>
        </ol>
        <pre><code>API_ID=123456
API_HASH=abcdef123456
TELEGRAM_BOT_TOKEN=123456:ABC-DEF
MONGO_DB_URI=mongodb+srv://user:pass@cluster0.mongodb.net/?retryWrites=true&amp;w=majority
LOG_CHANNEL_ID=-1002717243409
PORT=8000</code></pre>
        <div class="muted">Get API ID &amp; HASH from <a href="https://my.telegram.org" target="_blank" rel="noopener">my.telegram.org</a> and create bot via <a href="https://t.me/BotFather" target="_blank" rel="noopener">@BotFather</a>.</div>
        <ol start="3">
          <li>Run:</li>
        </ol>
        <pre><code>python main.py</code></pre>
      </div>
    </section>

    <section class="card">
      <h2>💬 Commands (Owner/Admin)</h2>
      <pre><code>/start
/help
/settings
/free (reply)
/unfree (reply)
/freelist
/tictac @user1 @user2
/lock @username secret message
/secretchat @username hi
/tagall message
/onlinetag message
/admin message
/tagstop
/checkperms
/addabuse word
/stats
/broadcast
/cleartempdata</code></pre>
      <div class="muted">Note: Some commands require admin rights in the group.</div>
    </section>

    <section class="grid grid-2">
      <div class="card">
        <h2>🛠 Tech</h2>
        <ul>
          <li>Python 3.11+, Pyrogram client</li>
          <li>MongoDB for persistence</li>
          <li>Flask health-check for uptime</li>
          <li>Ready for Koyeb / Railway</li>
        </ul>
        <span class="tag">Anti-Abuse</span>
        <span class="tag">Anti-Link</span>
        <span class="tag">Warn/Mute/Ban</span>
        <span class="tag">TagAll</span>
        <span class="tag">Games</span>
      </div>
      <div class="card">
        <h2>📞 Support</h2>
        <p>
          <strong>Update Channel:</strong> <a href="https://t.me/asbhai_bsr" target="_blank" rel="noopener">Join</a><br/>
          <strong>Support Group:</strong> <a href="https://t.me/askiangelbot" target="_blank" rel="noopener">Get Help</a><br/>
          <strong>Donation (UPI):</strong> <code>arsadsaifi8272@ibl</code><br/>
          <strong>Developer:</strong> <a href="https://t.me/asprmotion" target="_blank" rel="noopener">DM</a>
        </p>
      </div>
    </section>

    <section class="card">
      <h2>🪪 License</h2>
      <p>MIT © <a href="https://github.com/asbhai" target="_blank" rel="noopener">AS Bhai</a> — fork, modify &amp; deploy freely.</p>
    </section>

    <p class="footer">Made with ❤️ for Telegram communities.</p>
  </div>
</body>
</html>
