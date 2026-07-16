"""Pre-built project templates for JARVIS Builder.

Each template returns a dict {filepath: content} ready to be saved
as a project's `files` map.
"""
from __future__ import annotations
from typing import Dict, List


def list_templates() -> List[Dict[str, str]]:
    return [
        {"id": "blank", "name": "Em branco", "description": "Esqueleto mínimo (HTML + CSS + JS)."},
        {"id": "landing", "name": "Landing Page", "description": "Hero, features, CTA e footer modernos."},
        {"id": "dashboard", "name": "Dashboard", "description": "Painel analítico com cards, gráfico e tabela."},
        {"id": "game", "name": "Jogo (Snake)", "description": "Snake clássico em canvas com controles."},
        {"id": "blog", "name": "Blog", "description": "Lista de posts e página de leitura."},
    ]


def get_template_files(template_id: str, project_name: str = "Projeto") -> Dict[str, str]:
    name = project_name.strip() or "Projeto"
    tpl = (template_id or "blank").lower()
    if tpl == "landing":
        return _landing(name)
    if tpl == "dashboard":
        return _dashboard(name)
    if tpl == "game":
        return _game(name)
    if tpl == "blog":
        return _blog(name)
    return _blank(name)


def _shell(name: str, body: str, app_js: str = "", extra_head: str = "") -> Dict[str, str]:
    safe = name.replace('"', "'")
    head = (
        f"  <meta charset=\"utf-8\" />\n"
        f"  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />\n"
        f"  <title>{safe}</title>\n"
        f"  <script src=\"https://cdn.tailwindcss.com\"></script>\n"
        f"  <link rel=\"stylesheet\" href=\"styles.css\" />\n"
        f"{extra_head}"
    )
    html = (
        "<!doctype html>\n<html lang=\"pt-BR\">\n<head>\n"
        f"{head}"
        "</head>\n<body>\n"
        f"{body}\n"
        "  <script src=\"app.js\"></script>\n"
        "</body>\n</html>\n"
    )
    return {
        "index.html": html,
        "styles.css": "html, body { font-family: 'Inter', system-ui, sans-serif; }\n",
        "app.js": app_js or "// JS do projeto\nconsole.log('App pronto');\n",
    }


def _blank(name: str) -> Dict[str, str]:
    body = (
        '<main class="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center p-8">\n'
        '  <div class="text-center max-w-xl">\n'
        f'    <h1 class="text-4xl font-bold text-cyan-300 mb-3">{name}</h1>\n'
        '    <p class="text-slate-400">Projeto em branco. Peça ao JARVIS Builder para evoluir.</p>\n'
        '  </div>\n'
        '</main>'
    )
    return _shell(name, body)


def _landing(name: str) -> Dict[str, str]:
    body = f"""<header class="sticky top-0 z-20 backdrop-blur bg-slate-950/70 border-b border-slate-800">
    <div class="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
      <div class="flex items-center gap-2 text-cyan-300 font-bold tracking-widest">⚡ {name}</div>
      <nav class="flex gap-6 text-sm text-slate-300">
        <a href="#features" class="hover:text-cyan-300">Recursos</a>
        <a href="#pricing" class="hover:text-cyan-300">Preços</a>
        <a href="#contact" class="hover:text-cyan-300">Contato</a>
      </nav>
      <a href="#cta" class="px-4 py-2 rounded bg-cyan-500/20 border border-cyan-400/50 text-cyan-200 hover:bg-cyan-500/30 transition">Começar</a>
    </div>
  </header>

  <section class="max-w-6xl mx-auto px-6 py-24 text-center">
    <h1 class="text-5xl md:text-6xl font-bold text-white leading-tight mb-4">A próxima geração de <span class="text-cyan-300">{name}</span></h1>
    <p class="text-slate-300 max-w-2xl mx-auto mb-8">Construa, lance e escale produtos digitais com velocidade impressionante e estilo refinado.</p>
    <div class="flex gap-3 justify-center">
      <a href="#cta" class="px-6 py-3 rounded bg-cyan-500 text-slate-950 font-semibold hover:bg-cyan-400 transition">Teste grátis</a>
      <a href="#features" class="px-6 py-3 rounded border border-slate-700 text-slate-200 hover:border-cyan-400/60 transition">Saber mais</a>
    </div>
  </section>

  <section id="features" class="max-w-6xl mx-auto px-6 py-16 grid md:grid-cols-3 gap-6">
    <div class="p-6 rounded-xl border border-slate-800 bg-slate-900/40">
      <div class="text-cyan-300 text-2xl mb-2">□</div>
      <h3 class="font-semibold text-white mb-1">Rápido</h3>
      <p class="text-slate-400 text-sm">Performance de classe mundial em todos os dispositivos.</p>
    </div>
    <div class="p-6 rounded-xl border border-slate-800 bg-slate-900/40">
      <div class="text-cyan-300 text-2xl mb-2">○</div>
      <h3 class="font-semibold text-white mb-1">Seguro</h3>
      <p class="text-slate-400 text-sm">Criptografia, auditoria e conformidade desde o primeiro dia.</p>
    </div>
    <div class="p-6 rounded-xl border border-slate-800 bg-slate-900/40">
      <div class="text-cyan-300 text-2xl mb-2">△</div>
      <h3 class="font-semibold text-white mb-1">Escalável</h3>
      <p class="text-slate-400 text-sm">De startup a enterprise sem trocar de stack.</p>
    </div>
  </section>

  <section id="cta" class="max-w-6xl mx-auto px-6 py-20 text-center">
    <div class="rounded-2xl border border-cyan-500/30 bg-cyan-500/5 p-10">
      <h2 class="text-3xl font-bold text-white mb-2">Pronto para começar?</h2>
      <p class="text-slate-300 mb-6">Crie sua conta em segundos. Sem cartão.</p>
      <button id="signup" class="px-6 py-3 rounded bg-cyan-500 text-slate-950 font-semibold hover:bg-cyan-400 transition">Criar conta</button>
      <div id="msg" class="mt-3 text-cyan-300 text-sm"></div>
    </div>
  </section>

  <footer class="border-t border-slate-800 py-8 text-center text-slate-500 text-sm">
    © {name} — Todos os direitos reservados.
  </footer>
"""
    app_js = (
        "document.getElementById('signup').addEventListener('click',()=>{\n"
        "  document.getElementById('msg').textContent='Quase lá! Conexão de demo. Configure seu backend para finalizar o cadastro.';\n"
        "});\n"
    )
    out = _shell(name, '<body class="bg-slate-950 text-slate-100 min-h-screen">' + body + '</body>', app_js)
    # we wrapped <body> inside body() string above by mistake; fix:
    out["index.html"] = out["index.html"].replace('<body>\n<body class=', '<body class=').replace('</body>\n  <script src=', '</body>\n<script src=')
    return out


def _dashboard(name: str) -> Dict[str, str]:
    body = f"""<div class="min-h-screen bg-slate-950 text-slate-100 flex">
    <aside class="w-56 bg-slate-900/70 border-r border-slate-800 p-4 hidden md:block">
      <div class="text-cyan-300 font-bold tracking-widest mb-6">{name}</div>
      <nav class="space-y-2 text-sm">
        <a class="block px-3 py-2 rounded bg-cyan-500/10 text-cyan-300" href="#">Visão geral</a>
        <a class="block px-3 py-2 rounded hover:bg-slate-800/60" href="#">Vendas</a>
        <a class="block px-3 py-2 rounded hover:bg-slate-800/60" href="#">Clientes</a>
        <a class="block px-3 py-2 rounded hover:bg-slate-800/60" href="#">Relatórios</a>
      </nav>
    </aside>
    <main class="flex-1 p-6">
      <h1 class="text-2xl font-semibold mb-4">Visão geral</h1>
      <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div class="p-4 rounded-xl bg-slate-900/60 border border-slate-800"><div class="text-slate-400 text-xs">Receita</div><div class="text-2xl font-bold text-emerald-400">R$ 124.380</div></div>
        <div class="p-4 rounded-xl bg-slate-900/60 border border-slate-800"><div class="text-slate-400 text-xs">Pedidos</div><div class="text-2xl font-bold">1.284</div></div>
        <div class="p-4 rounded-xl bg-slate-900/60 border border-slate-800"><div class="text-slate-400 text-xs">Clientes</div><div class="text-2xl font-bold">842</div></div>
        <div class="p-4 rounded-xl bg-slate-900/60 border border-slate-800"><div class="text-slate-400 text-xs">Conv.</div><div class="text-2xl font-bold text-cyan-300">4.2%</div></div>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div class="col-span-2 p-4 rounded-xl bg-slate-900/60 border border-slate-800">
          <h3 class="text-sm text-slate-400 mb-2">Vendas (7 dias)</h3>
          <canvas id="chart" height="160"></canvas>
        </div>
        <div class="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
          <h3 class="text-sm text-slate-400 mb-2">Top produtos</h3>
          <ul id="top" class="space-y-2 text-sm"></ul>
        </div>
      </div>
    </main>
  </div>"""
    app_js = (
        "const data=[12,19,14,22,28,24,31];const labels=['Seg','Ter','Qua','Qui','Sex','Sáb','Dom'];\n"
        "const c=document.getElementById('chart');const ctx=c.getContext('2d');const W=c.clientWidth;const H=c.height;\n"
        "c.width=W;const max=Math.max(...data);const step=W/(data.length-1);\n"
        "ctx.strokeStyle='#22d3ee';ctx.lineWidth=2;ctx.beginPath();data.forEach((v,i)=>{const x=i*step;const y=H- (v/max)*(H-20)-10;if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);});ctx.stroke();\n"
        "ctx.fillStyle='#94a3b8';ctx.font='10px sans-serif';labels.forEach((l,i)=>ctx.fillText(l,i*step,H-2));\n"
        "const top=document.getElementById('top');[['Produto A',38],['Produto B',24],['Produto C',19],['Produto D',12]].forEach(([n,p])=>{const li=document.createElement('li');li.className='flex justify-between';li.innerHTML='<span>'+n+'</span><span class=\"text-cyan-300\">'+p+'%</span>';top.appendChild(li);});\n"
    )
    return _shell(name, body, app_js)


def _game(name: str) -> Dict[str, str]:
    body = f"""<div class="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-6 gap-3">
    <h1 class="text-2xl font-bold text-cyan-300">{name} — Snake</h1>
    <p class="text-slate-400 text-sm">Use as setas (← → ↑ ↓) ou WASD para jogar.</p>
    <canvas id="game" width="400" height="400" class="rounded-lg border border-cyan-500/30 bg-black"></canvas>
    <div class="text-sm text-slate-300">Pontuação: <span id="score" class="text-cyan-300 font-bold">0</span></div>
    <button id="restart" class="px-3 py-1 rounded border border-cyan-500/40 text-cyan-200 hover:bg-cyan-500/20">Reiniciar</button>
  </div>"""
    app_js = r"""const c=document.getElementById('game');const ctx=c.getContext('2d');const G=20;const S=c.width/G;
let snake,dir,food,score,running,timer;
function reset(){snake=[{x:10,y:10}];dir={x:1,y:0};food=spawn();score=0;running=true;document.getElementById('score').textContent=0;if(timer)clearInterval(timer);timer=setInterval(loop,100);}
function spawn(){return{x:Math.floor(Math.random()*G),y:Math.floor(Math.random()*G)};}
function loop(){if(!running)return;const head={x:snake[0].x+dir.x,y:snake[0].y+dir.y};if(head.x<0||head.x>=G||head.y<0||head.y>=G||snake.some(s=>s.x===head.x&&s.y===head.y)){running=false;ctx.fillStyle='#ef4444';ctx.font='20px sans-serif';ctx.fillText('Fim de jogo',140,200);return;}
snake.unshift(head);if(head.x===food.x&&head.y===food.y){score++;document.getElementById('score').textContent=score;food=spawn();}else snake.pop();
ctx.fillStyle='#020617';ctx.fillRect(0,0,c.width,c.height);ctx.fillStyle='#22d3ee';snake.forEach(s=>ctx.fillRect(s.x*S,s.y*S,S-1,S-1));ctx.fillStyle='#f59e0b';ctx.fillRect(food.x*S,food.y*S,S-1,S-1);}
window.addEventListener('keydown',e=>{const k=e.key.toLowerCase();if((k==='arrowup'||k==='w')&&dir.y===0)dir={x:0,y:-1};else if((k==='arrowdown'||k==='s')&&dir.y===0)dir={x:0,y:1};else if((k==='arrowleft'||k==='a')&&dir.x===0)dir={x:-1,y:0};else if((k==='arrowright'||k==='d')&&dir.x===0)dir={x:1,y:0};});
document.getElementById('restart').addEventListener('click',reset);reset();
"""
    return _shell(name, body, app_js)


def _blog(name: str) -> Dict[str, str]:
    body = f"""<header class="border-b border-slate-800 bg-slate-950">
    <div class="max-w-3xl mx-auto px-6 py-6">
      <div class="text-cyan-300 text-sm tracking-widest">{name}</div>
      <h1 class="text-3xl font-bold mt-1">Reflexões sobre tecnologia, design e futuro.</h1>
    </div>
  </header>
  <main class="max-w-3xl mx-auto px-6 py-10" id="feed"></main>
  <article id="post" class="max-w-3xl mx-auto px-6 py-10 hidden">
    <button id="back" class="text-cyan-300 text-sm mb-4">← voltar</button>
    <h2 id="ptitle" class="text-3xl font-bold mb-3"></h2>
    <div id="pmeta" class="text-slate-400 text-sm mb-6"></div>
    <div id="pbody" class="prose prose-invert max-w-none"></div>
  </article>"""
    app_js = r"""const posts=[{id:1,title:'O futuro é multimodal',author:'JARVIS',date:'2025-07-01',excerpt:'Por que LLMs deixarão de ser apenas texto.',body:'Texto longo descrevendo a transição para modelos multimodais que entendem vídeo, áudio, código e imagens simultaneamente.'},
{id:2,title:'Cyberpunk minimalista',author:'JARVIS',date:'2025-07-03',excerpt:'Como aplicar estética futurista sem sobrecarregar.',body:'O cyberpunk minimalista privilegia contraste alto, ruído sutil e tipografia mono. Use parcimoniosamente.'},
{id:3,title:'Atalhos de teclado que mudam tudo',author:'JARVIS',date:'2025-07-05',excerpt:'Pequenas vitórias diárias.',body:'Listamos os atalhos mais subutilizados no VS Code, Chrome e em sistemas operacionais modernos.'}];
const feed=document.getElementById('feed');const article=document.getElementById('post');
function renderFeed(){feed.innerHTML=posts.map(p=>`<article class="py-5 border-b border-slate-800"><a href="#" data-id="${p.id}" class="block hover:bg-slate-900/40 rounded p-2 -m-2"><div class="text-xs text-cyan-400">${p.date} — ${p.author}</div><h2 class="text-xl font-semibold mt-1">${p.title}</h2><p class="text-slate-400 mt-1">${p.excerpt}</p></a></article>`).join('');feed.querySelectorAll('a').forEach(a=>a.addEventListener('click',e=>{e.preventDefault();open(parseInt(a.dataset.id))}));}
function open(id){const p=posts.find(x=>x.id===id);if(!p)return;feed.classList.add('hidden');article.classList.remove('hidden');document.getElementById('ptitle').textContent=p.title;document.getElementById('pmeta').textContent=`${p.date} por ${p.author}`;document.getElementById('pbody').textContent=p.body;}
document.getElementById('back').addEventListener('click',()=>{article.classList.add('hidden');feed.classList.remove('hidden');});renderFeed();
"""
    return _shell(name, '<body class="bg-slate-950 text-slate-100 min-h-screen">' + body + '</body>', app_js)
