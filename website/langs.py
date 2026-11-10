"""The website's pages in German, Russian, Portuguese (Brazil), Spanish (Latin America) and Chinese (13/10, the app in
seven languages): the home page, the privacy policy and the terms, translated from the English ones of website/build.py. Each
text is a function of C (the publisher, contact, host, GitHub, update date) and, for the home page, the download
block. The legal pages say the French version prevails (French law governs them)."""

UI = {
    "de": {"dl": "Herunterladen", "how": "So funktioniert's", "priv": "Datenschutz", "terms": "Nutzungsbedingungen", "lic": "Lizenzen",
           "valve": "Nicht mit der Valve Corporation verbunden.", "soon": "Demnächst", "lang": "Sprache"},
    "ru": {"dl": "Скачать", "how": "Как это работает", "priv": "Конфиденциальность", "terms": "Условия", "lic": "Лицензии",
           "valve": "Не связано с Valve Corporation.", "soon": "Скоро", "lang": "Язык"},
    "pt": {"dl": "Baixar", "how": "Como funciona", "priv": "Privacidade", "terms": "Termos", "lic": "Licenças",
           "valve": "Não afiliado à Valve Corporation.", "soon": "Em breve", "lang": "Idioma"},
    "es": {"dl": "Descargar", "how": "Cómo funciona", "priv": "Privacidad", "terms": "Términos", "lic": "Licencias",
           "valve": "No afiliado a Valve Corporation.", "soon": "Próximamente", "lang": "Idioma"},
    "zh": {"dl": "下载", "how": "使用方法", "priv": "隐私", "terms": "条款", "lic": "许可证",
           "valve": "与Valve Corporation无关联。", "soon": "即将推出", "lang": "语言"},
}

DESC = {
    "de": "Wily, dein CS2-Coach: Live-Tipps auf deinem zweiten Bildschirm, ein Aufwärmen mit Bots in deinen eigenen Situationen und die Auswertung deiner Matches.",
    "ru": "Wily, твой коуч по CS2: советы в реальном времени на втором экране, разминка с ботами на твоих ситуациях и разбор твоих матчей.",
    "pt": "Wily, seu coach de CS2: dicas ao vivo na segunda tela, um aquecimento com bots nas suas situações e a revisão das suas partidas.",
    "es": "Wily, tu coach de CS2: consejos en vivo en tu segunda pantalla, un calentamiento con bots en tus situaciones y el repaso de tus partidas.",
    "zh": "Wily，你的CS2教练：第二块屏幕上的实时建议、针对你自身局面的人机热身，以及比赛复盘。",
}
TITLE = {
    "de": ("Wily · dein CS2-Coach auf dem zweiten Bildschirm", "Datenschutzerklärung · Wily", "Nutzungsbedingungen · Wily"),
    "ru": ("Wily · твой коуч по CS2 на втором экране", "Политика конфиденциальности · Wily", "Условия использования · Wily"),
    "pt": ("Wily · seu coach de CS2 na segunda tela", "Política de privacidade · Wily", "Termos de uso · Wily"),
    "es": ("Wily · tu coach de CS2 en tu segunda pantalla", "Política de privacidad · Wily", "Términos de uso · Wily"),
    "zh": ("Wily · 第二块屏幕上的CS2教练", "隐私政策 · Wily", "使用条款 · Wily"),
}
UPDATED = {"de": "13. Oktober 2026", "ru": "13 октября 2026 г.", "pt": "13 de outubro de 2026", "es": "13 de octubre de 2026", "zh": "2026年10月13日"}
PREVAILS = {
    "de": "Übersetzung zu deiner Information. Bei Abweichungen gilt die französische Fassung.",
    "ru": "Перевод для удобства. При расхождении преимущественную силу имеет французская версия.",
    "pt": "Tradução para sua conveniência. Em caso de divergência, prevalece a versão em francês.",
    "es": "Traducción para tu comodidad. En caso de diferencia, prevalece la versión en francés.",
    "zh": "本译文仅为方便阅读。如有出入，以法文版本为准。",
}

# the download block: the button, the version line, Windows' SmartScreen words in the player's Windows language
DL = {
    "de": {"btn": "Wily für Windows herunterladen", "zip_btn": "Für Windows herunterladen · {mb} MB", "ver": "Version {app} · {when} · Datenbank aus {n} Matches",
           "parts": "das Setup lädt {mb} MB herunter",
           "smart": "Wenn Windows <i>„Der Computer wurde durch Windows geschützt“</i> anzeigt: Klick auf <b>Weitere Informationen</b>, dann auf <b>Trotzdem ausführen</b>. Die App ist noch nicht mit einem kostenpflichtigen Zertifikat signiert; jeder Teil, den sie herunterlädt, wird mit der Signatur ihres Autors geprüft.",
           "sha_setup": "SHA-256 des Setups", "or_zip": "oder <a href=\"{href}\" download>das Zip</a> ({mb} MB, selbst entpacken)",
           "linux": "<b>Linux</b> (Match-Auswertung und Live; der Trainingsserver ist dort experimentell und wird in den Einstellungen eingeschaltet): Lade <a href=\"{href}\" download>wily-linux.sh</a> herunter, dann im Terminal <code>sh wily-linux.sh</code> (Python 3.11 oder neuer). SHA-256: <span class=\"mono\">{sha}</span>",
           "sep": ".", "date": "%d.%m.%Y"},
    "ru": {"btn": "Скачать Wily для Windows", "zip_btn": "Скачать для Windows · {mb} МБ", "ver": "Версия {app} · {when} · база из {n} матчей",
           "parts": "установщик скачает {mb} МБ",
           "smart": "Если Windows пишет <i>«Система Windows защитила ваш компьютер»</i>: нажми <b>Подробнее</b>, затем <b>Выполнить в любом случае</b>. Приложение пока не подписано платным сертификатом; каждая скачанная часть проверяется подписью его автора.",
           "sha_setup": "SHA-256 установщика", "or_zip": "или <a href=\"{href}\" download>zip-архив</a> ({mb} МБ, распаковать самому)",
           "linux": "<b>Linux</b> (разбор матчей и Live; сервер тренировок там экспериментальный, включается в Настройках): скачай <a href=\"{href}\" download>wily-linux.sh</a>, затем в терминале <code>sh wily-linux.sh</code> (Python 3.11 или новее). SHA-256: <span class=\"mono\">{sha}</span>",
           "sep": " ", "date": "%d.%m.%Y"},
    "pt": {"btn": "Baixar o Wily para Windows", "zip_btn": "Baixar para Windows · {mb} MB", "ver": "Versão {app} · {when} · base de {n} partidas",
           "parts": "o instalador baixa {mb} MB",
           "smart": "Se o Windows mostrar <i>\"O Windows protegeu o computador\"</i>: clique em <b>Mais informações</b> e depois em <b>Executar assim mesmo</b>. O app ainda não é assinado com um certificado pago; cada parte que ele baixa é verificada com a assinatura do autor.",
           "sha_setup": "SHA-256 do instalador", "or_zip": "ou <a href=\"{href}\" download>o zip</a> ({mb} MB, para descompactar você mesmo)",
           "linux": "<b>Linux</b> (revisão das partidas e Ao vivo; o servidor de treino é experimental lá, para ligar nas Configurações): baixe <a href=\"{href}\" download>wily-linux.sh</a> e, num terminal, <code>sh wily-linux.sh</code> (Python 3.11 ou mais recente). SHA-256: <span class=\"mono\">{sha}</span>",
           "sep": ".", "date": "%d/%m/%Y"},
    "es": {"btn": "Descargar Wily para Windows", "zip_btn": "Descargar para Windows · {mb} MB", "ver": "Versión {app} · {when} · base de {n} partidas",
           "parts": "el instalador descarga {mb} MB",
           "smart": "Si Windows muestra <i>\"Windows protegió su PC\"</i>: haz clic en <b>Más información</b> y luego en <b>Ejecutar de todas formas</b>. La app todavía no está firmada con un certificado de pago; cada parte que descarga se verifica con la firma de su autor.",
           "sha_setup": "SHA-256 del instalador", "or_zip": "o <a href=\"{href}\" download>el zip</a> ({mb} MB, para descomprimir tú mismo)",
           "linux": "<b>Linux</b> (repaso de partidas y En vivo; el servidor de entrenamiento es experimental ahí, se activa en Ajustes): descarga <a href=\"{href}\" download>wily-linux.sh</a> y luego, en una terminal, <code>sh wily-linux.sh</code> (Python 3.11 o más reciente). SHA-256: <span class=\"mono\">{sha}</span>",
           "sep": ".", "date": "%d/%m/%Y"},
    "zh": {"btn": "下载Windows版Wily", "zip_btn": "下载Windows版 · {mb} MB", "ver": "版本 {app} · {when} · 数据库共{n}场比赛",
           "parts": "安装程序会下载{mb} MB",
           "smart": "如果Windows显示<i>“Windows 已保护你的电脑”</i>：点击<b>更多信息</b>，然后点击<b>仍要运行</b>。本应用尚未使用付费证书签名；它下载的每个部分都会用作者的签名校验。",
           "sha_setup": "安装程序的SHA-256", "or_zip": "或<a href=\"{href}\" download>zip压缩包</a>（{mb} MB，需自行解压）",
           "linux": "<b>Linux</b>（比赛复盘和实时页；训练服务器在Linux上为实验功能，需在设置中开启）：下载<a href=\"{href}\" download>wily-linux.sh</a>，然后在终端运行<code>sh wily-linux.sh</code>（需要Python 3.11或更高版本）。SHA-256：<span class=\"mono\">{sha}</span>",
           "sep": ",", "date": "%Y-%m-%d"},
}


def home_ru(C, dl):
    return f"""
<h1>Привет, я Wily.</h1>
<p class="lede">Твой коуч по CS2. Я ставлю ботов ровно туда, где тебя убили в твоих настоящих матчах, прямо в CS2, чтобы ты переигрывал дуэль, пока не выиграешь. Во время матчей я даю советы в реальном времени на втором экране, а после честно говорю, что исправить. Я учусь на твоих демках и на базе из тысяч матчей. Бесплатная альфа с открытым кодом для Windows и Linux: первая версия, открытая для всех, так что шероховатости будут.</p>
<section id="download">{dl}<p class="note"><b>Открытый код</b> (Apache 2.0): весь код приложения на <a href="{C['github']}">GitHub</a>. Каждая версия публикуется и там, с тем же SHA-256, что на этой странице, и привязана к точному коммиту, из которого собрана: <a href="{C['github']}/releases">версии</a>.</p></section>
<div class="grid">
 <article class="card"><span class="eyebrow">Live</span><h3>Во время матча</h3><ul><li>Что купить в этом раунде и в следующем</li><li>Куда, скорее всего, пойдут T — с учётом таймера и того, что ты видишь</li><li>Твои пути и сильные точки на радаре, гранаты, которые стоит кинуть сейчас</li></ul></article>
 <article class="card"><span class="eyebrow">Подготовка</span><h3>Перед игрой</h3><ul><li>Разминка на твоих слабых местах, от 5 минут (до 45)</li><li>Сервер тренировок с ботами, которые повторяют твои настоящие смерти и клатчи</li></ul></article>
 <article class="card"><span class="eyebrow">Разбор</span><h3>После сессии</h3><ul><li>Что изменилось по сравнению с прошлыми матчами и почему</li><li>Твой фокус недели и эксперименты, которые стоит попробовать</li><li>Каждый матч по раундам</li></ul></article>
</div>
<h2 id="see">Как это выглядит</h2>
<div class="shots">
 <figure><video src="media/deaths.mp4" poster="media/deaths.jpg" autoplay muted loop playsinline preload="metadata"></video><figcaption><b>Твои собственные смерти, заново.</b> Боты возвращаются ровно туда, откуда убили тебя в настоящем матче (здесь 3-й раунд на Nuke, Hut Roof, твой путь синим): переигрывай дуэль, пока не выиграешь.</figcaption></figure>
 <figure><video src="media/live.mp4" poster="media/live.jpg" autoplay muted loop playsinline preload="metadata"></video><figcaption><b>Live</b> на втором экране, раунд на Nuke (×6): после плэнта, затем план следующего раунда с шансами, путями и гранатами на радаре.</figcaption></figure>
 <figure><video src="media/training.mp4" poster="media/training.jpg" autoplay muted loop playsinline preload="metadata"></video><figcaption><b>Сервер тренировок</b>, упражнение с гранатой на Mirage: где встать, куда целиться и долетела ли она вовремя.</figcaption></figure>
 <figure><img src="media/prepare.jpg" alt="Страница «Подготовка»: карты для тренировки, раунды, которые ты проигрываешь в последнее время, блоки разминки и твой уровень" loading="lazy"><figcaption><b>Подготовка</b>: разминка начинается там, где ты проигрываешь раунды в последнее время.</figcaption></figure>
</div>
<h2 id="how">Как это работает</h2>
<ol class="steps">
 <li>Открой <b>WilySetup.exe</b>, затем <b>Install</b>: он скачает меня, проверит каждую часть и установит для твоей учётной записи Windows (без прав администратора). Я запускаюсь вместе с Windows и сам открываю Live, когда запускается CS2.</li>
 <li>При первом запуске три шага: твой аккаунт Steam (я его нахожу), подключение CS2 (вставить один параметр запуска), код истории матчей (ключ Steam создавать не нужно). Потом твои матчи анализируются на твоём ПК, по несколько минут каждый.</li>
 <li>Подготовка → <b>Разминка</b>: сервер тренировок устанавливается, только когда ты впервые его открываешь, и работает на файлах твоей CS2 (ссылки: без второй загрузки, без лишнего места на диске).</li>
</ol>
<p class="note">Нужны Windows 10 или 11 (64 бита) или Linux (Python 3.11+), CS2 в Steam, ПК с 8 ГБ оперативной памяти (для игры и Wily вместе) и место для твоих демок (около 250 МБ на матч). Приложение говорит на русском, английском, французском, немецком, португальском, испанском и китайском.</p>
<h2>Честная игра и конфиденциальность</h2>
<div class="grid">
 <article class="card"><h3>Только то, что даёт Valve</h3><p>Game State Integration (официальная функция игры для HUD и RGB-клавиатур), лог консоли, который пишет CS2, Steam Web API, демки твоих матчей. Я никогда не читаю память игры и её сетевой трафик и никогда не играю за тебя. Сервер тренировок — локальная копия игры, в которую заходишь только ты. Всё это можно проверить: <a href="{C['github']}">код открыт</a>.</p></article>
 <article class="card"><h3>Что остаётся здесь, чем делимся</h3><p>Твои демки, профиль, коды Steam и голос никогда не покидают твой ПК (без собственного ключа Steam список твоих матчей идёт к Steam через этот сайт, ничего не сохраняется). <b>По умолчанию отправляется, в обезличенном виде:</b> таблицы, которые я извлекаю из твоих новых матчей (позиции, дуэли, гранаты, закупки, раунды; каждый SteamID заменён случайным идентификатором, без ников и без ID матча), чтобы пополнять базу, и анонимные счётчики использования. При первом запуске я об этом скажу, и один клик выключает и то и другое (или позже в Настройках). <a href="ru-privacy.html">Политика конфиденциальности</a></p></article>
 <article class="card"><h3>Бесплатная альфа</h3><p>Бесплатно на время тестов. Это первая версия, открытая для всех игроков: расскажи, что ломается, через метку <b>alpha · report</b> вверху моей страницы (ты видишь, что отправляется) или по почте. Мои обновления подписаны моим автором, и я проверяю их перед установкой. Вопросы и баги: <a href="mailto:{C['contact']}">{C['contact']}</a>.</p></article>
</div>
"""


def home_pt(C, dl):
    return f"""
<h1>Oi, eu sou o Wily.</h1>
<p class="lede">Seu coach de CS2. Eu coloco bots exatamente onde te mataram nas suas partidas de verdade, dentro do próprio CS2, para você jogar o duelo de novo até vencer. Durante as partidas, dou dicas ao vivo na sua segunda tela e, depois, te digo com clareza o que corrigir. Eu aprendo com as suas demos e com uma base de milhares de partidas. Alpha grátis e open source para Windows e Linux: a primeira versão aberta a todos, então ainda tem arestas para aparar.</p>
<section id="download">{dl}<p class="note"><b>Open source</b> (Apache 2.0): todo o código do app está no <a href="{C['github']}">GitHub</a>. Cada versão também é publicada lá, com o mesmo SHA-256 desta página, ligada ao commit exato de onde foi gerada: <a href="{C['github']}/releases">versões</a>.</p></section>
<div class="grid">
 <article class="card"><span class="eyebrow">Ao vivo</span><h3>Durante a partida</h3><ul><li>O que comprar neste round e no próximo</li><li>Para onde os Ts devem ir, atualizado com o relógio e com o que você vê</li><li>Seus caminhos e seus spots fortes no radar, as granadas que valem a pena agora</li></ul></article>
 <article class="card"><span class="eyebrow">Preparar</span><h3>Antes de jogar</h3><ul><li>Um aquecimento montado nos seus pontos fracos, a partir de 5 minutos (até 45)</li><li>Um servidor de treino com bots que repetem suas mortes e seus clutches de verdade</li></ul></article>
 <article class="card"><span class="eyebrow">Revisão</span><h3>Depois da sessão</h3><ul><li>O que mudou em relação às suas partidas anteriores, e por quê</li><li>Seu foco da semana e os testes para tentar</li><li>Cada partida, round a round</li></ul></article>
</div>
<h2 id="see">Veja</h2>
<div class="shots">
 <figure><video src="media/deaths.mp4" poster="media/deaths.jpg" autoplay muted loop playsinline preload="metadata"></video><figcaption><b>Suas próprias mortes, repetidas.</b> Os bots voltam exatamente de onde te mataram na partida real (aqui o round 3 na Nuke, Hut Roof, seu caminho em azul): jogue o duelo de novo até vencer.</figcaption></figure>
 <figure><video src="media/live.mp4" poster="media/live.jpg" autoplay muted loop playsinline preload="metadata"></video><figcaption><b>Ao vivo</b> na segunda tela, um round na Nuke (6× mais rápido): depois do plant, e o plano do round seguinte com as chances, os caminhos e as granadas no radar.</figcaption></figure>
 <figure><video src="media/training.mp4" poster="media/training.jpg" autoplay muted loop playsinline preload="metadata"></video><figcaption><b>Servidor de treino</b>, um exercício de granada na Mirage: onde ficar, onde mirar e se ela caiu a tempo.</figcaption></figure>
 <figure><img src="media/prepare.jpg" alt="A página Preparar: mapas para treinar, os rounds que você anda perdendo, os blocos de aquecimento e seu nível" loading="lazy"><figcaption><b>Preparar</b>: o aquecimento começa onde você anda perdendo rounds.</figcaption></figure>
</div>
<h2 id="how">Como funciona</h2>
<ol class="steps">
 <li>Abra o <b>WilySetup.exe</b> e clique em <b>Install</b>: ele me baixa, confere cada parte e me instala na sua conta do Windows (sem direitos de administrador). Eu abro junto com o Windows e abro o Ao vivo sozinho quando o CS2 inicia.</li>
 <li>Na primeira vez, três passos: sua conta Steam (eu encontro), o CS2 conectado (uma opção de inicialização para colar), seu código de histórico de partidas (nenhuma chave da Steam para criar). Depois suas partidas são analisadas no seu PC, alguns minutos cada.</li>
 <li>Preparar → <b>Aquecimento</b>: o servidor de treino só se instala na primeira vez que você o abre, e roda com os arquivos do seu CS2 (links: sem segundo download, sem ocupar espaço extra).</li>
</ol>
<p class="note">Precisa de Windows 10 ou 11 (64 bits) ou Linux (Python 3.11+), CS2 na Steam, um PC com 8 GB de RAM (para o jogo e o Wily juntos) e espaço para as suas demos (cerca de 250 MB por partida). O app fala português, inglês, francês, alemão, russo, espanhol e chinês.</p>
<h2>Jogo limpo e privacidade</h2>
<div class="grid">
 <article class="card"><h3>Só o que a Valve oferece</h3><p>O Game State Integration (o recurso oficial do jogo para HUDs e teclados RGB), o log de console que o CS2 escreve, a Steam Web API e as demos das suas partidas. Eu nunca leio a memória do jogo nem o tráfego de rede, e nunca jogo por você. O servidor de treino é uma cópia local do jogo em que só você entra. Dá para conferir tudo: <a href="{C['github']}">o código é público</a>.</p></article>
 <article class="card"><h3>O que fica aqui, o que é compartilhado</h3><p>Suas demos, seu perfil, seus códigos da Steam e sua voz nunca saem do seu PC (sem uma chave da Steam sua, a lista das suas partidas passa por este site até a Steam, e nada é guardado). <b>Compartilhado por padrão, anonimizado:</b> as tabelas que eu extraio das suas partidas novas (posições, duelos, granadas, compras, rounds; cada SteamID trocado por um id aleatório, sem nomes, sem id da partida), para fazer a base crescer, e contadores de uso anônimos. Na primeira vez eu te aviso, e um clique desliga os dois (ou depois, nas Configurações). <a href="pt-privacy.html">Política de privacidade</a></p></article>
 <article class="card"><h3>Alpha grátis</h3><p>Grátis enquanto está em teste. É a primeira versão aberta a todos os jogadores: me conte o que quebrar pela etiqueta <b>alpha · report</b> no topo da minha página (você vê o que é enviado) ou por e-mail. Minhas atualizações são assinadas pelo meu autor, e eu confiro antes de instalar qualquer coisa. Dúvidas ou bugs: <a href="mailto:{C['contact']}">{C['contact']}</a>.</p></article>
</div>
"""


def home_es(C, dl):
    return f"""
<h1>Hola, soy Wily.</h1>
<p class="lede">Tu coach de CS2. Pongo bots exactamente donde te mataron en tus partidas reales, dentro del propio CS2, para que vuelvas a jugar el duelo hasta ganarlo. Durante tus partidas te doy consejos en vivo en tu segunda pantalla y, después, te digo claramente qué corregir. Aprendo de tus demos y de una base de miles de partidas. Alpha gratis y de código abierto para Windows y Linux: la primera versión abierta a todos, así que todavía hay detalles por pulir.</p>
<section id="download">{dl}<p class="note"><b>Código abierto</b> (Apache 2.0): todo el código de la app está en <a href="{C['github']}">GitHub</a>. Cada versión también se publica ahí, con el mismo SHA-256 que en esta página, ligada al commit exacto con el que se construyó: <a href="{C['github']}/releases">versiones</a>.</p></section>
<div class="grid">
 <article class="card"><span class="eyebrow">En vivo</span><h3>Durante la partida</h3><ul><li>Qué comprar esta ronda y la siguiente</li><li>A dónde van a ir probablemente los Ts, actualizado con el reloj y con lo que ves</li><li>Tus caminos y tus spots fuertes en el radar, las granadas que conviene tirar ahora</li></ul></article>
 <article class="card"><span class="eyebrow">Preparar</span><h3>Antes de jugar</h3><ul><li>Un calentamiento armado sobre tus puntos débiles, desde 5 minutos (hasta 45)</li><li>Un servidor de entrenamiento con bots que repiten tus muertes y tus clutches reales</li></ul></article>
 <article class="card"><span class="eyebrow">Repaso</span><h3>Después de la sesión</h3><ul><li>Qué cambió frente a tus partidas anteriores, y por qué</li><li>Tu foco de la semana y las pruebas para intentar</li><li>Cada partida, ronda por ronda</li></ul></article>
</div>
<h2 id="see">Míralo</h2>
<div class="shots">
 <figure><video src="media/deaths.mp4" poster="media/deaths.jpg" autoplay muted loop playsinline preload="metadata"></video><figcaption><b>Tus propias muertes, repetidas.</b> Los bots vuelven exactamente a donde te mataron en tu partida real (aquí la ronda 3 en Nuke, Hut Roof, tu camino en azul): vuelve a jugar el duelo hasta ganarlo.</figcaption></figure>
 <figure><video src="media/live.mp4" poster="media/live.jpg" autoplay muted loop playsinline preload="metadata"></video><figcaption><b>En vivo</b> en la segunda pantalla, una ronda en Nuke (a 6×): después del plante, y luego el plan de la ronda siguiente con sus probabilidades, los caminos y las granadas en el radar.</figcaption></figure>
 <figure><video src="media/training.mp4" poster="media/training.jpg" autoplay muted loop playsinline preload="metadata"></video><figcaption><b>Servidor de entrenamiento</b>, un ejercicio de granada en Mirage: dónde pararse, dónde apuntar y si llegó a tiempo.</figcaption></figure>
 <figure><img src="media/prepare.jpg" alt="La página Preparar: mapas para entrenar, las rondas que estás perdiendo últimamente, los bloques de calentamiento y tu nivel" loading="lazy"><figcaption><b>Preparar</b>: el calentamiento empieza donde estás perdiendo rondas últimamente.</figcaption></figure>
</div>
<h2 id="how">Cómo funciona</h2>
<ol class="steps">
 <li>Abre <b>WilySetup.exe</b> y luego <b>Install</b>: me descarga, verifica cada parte y me instala para tu cuenta de Windows (sin permisos de administrador). Arranco con Windows y abro En vivo solo cuando arranca CS2.</li>
 <li>La primera vez, tres pasos: tu cuenta de Steam (yo la encuentro), CS2 conectado (una opción de lanzamiento para pegar), tu código de historial de partidas (ninguna clave de Steam que crear). Después tus partidas se analizan en tu PC, unos minutos cada una.</li>
 <li>Preparar → <b>Calentamiento</b>: el servidor de entrenamiento solo se instala la primera vez que lo abres, y funciona con los archivos de tu CS2 (enlaces: sin segunda descarga, sin espacio extra).</li>
</ol>
<p class="note">Necesitas Windows 10 u 11 (64 bits) o Linux (Python 3.11+), CS2 en Steam, un PC con 8 GB de RAM (para el juego y Wily juntos) y espacio para tus demos (unos 250 MB por partida). La app habla español, inglés, francés, alemán, ruso, portugués y chino.</p>
<h2>Juego limpio y privacidad</h2>
<div class="grid">
 <article class="card"><h3>Solo lo que Valve ofrece</h3><p>El Game State Integration (la función oficial del juego para HUDs y teclados RGB), el registro de consola que escribe CS2, la Steam Web API y las demos de tus partidas. Nunca leo la memoria del juego ni su tráfico de red, y nunca juego por ti. El servidor de entrenamiento es una copia local del juego a la que solo entras tú. Puedes comprobarlo todo: <a href="{C['github']}">el código es público</a>.</p></article>
 <article class="card"><h3>Lo que se queda aquí, lo que se comparte</h3><p>Tus demos, tu perfil, tus códigos de Steam y tu voz nunca salen de tu PC (sin una clave de Steam propia, la lista de tus partidas pasa por este sitio hasta Steam, sin que se guarde nada). <b>Compartido por defecto, anonimizado:</b> las tablas que extraigo de tus partidas nuevas (posiciones, duelos, granadas, compras, rondas; cada SteamID reemplazado por un id aleatorio, sin nombres, sin id de partida), para hacer crecer la base, y contadores de uso anónimos. La primera vez te lo digo, y un clic desactiva las dos cosas (o más tarde en Ajustes). <a href="es-privacy.html">Política de privacidad</a></p></article>
 <article class="card"><h3>Alpha gratis</h3><p>Gratis mientras se prueba. Es la primera versión abierta a todos los jugadores: cuéntame qué falla con la etiqueta <b>alpha · report</b> arriba de mi página (ves lo que se envía) o por correo. Mis actualizaciones están firmadas por mi autor, y las verifico antes de instalar nada. Preguntas o bugs: <a href="mailto:{C['contact']}">{C['contact']}</a>.</p></article>
</div>
"""


def home_zh(C, dl):
    return f"""
<h1>你好，我是Wily。</h1>
<p class="lede">你的CS2教练。我把机器人放回你在真实比赛中被击杀的位置，就在CS2里，让你重打那场对枪，直到赢下来。比赛中我在你的第二块屏幕上给你实时建议，赛后清楚地告诉你该改什么。我从你的录像和数千场比赛的数据库中学习。免费、开源的alpha版，支持Windows和Linux：这是第一个向所有人开放的版本，难免还有不完善的地方。</p>
<section id="download">{dl}<p class="note"><b>开源</b>（Apache 2.0）：应用的全部代码都在<a href="{C['github']}">GitHub</a>上。每个版本也在那里发布，SHA-256与本页相同，并对应构建它的确切提交：<a href="{C['github']}/releases">版本列表</a>。</p></section>
<div class="grid">
 <article class="card"><span class="eyebrow">实时</span><h3>比赛中</h3><ul><li>这回合和下回合该买什么</li><li>T方可能去哪里，随时钟和你看到的情况更新</li><li>雷达上你的路线和强势点位，以及现在值得扔的道具</li></ul></article>
 <article class="card"><span class="eyebrow">准备</span><h3>开打前</h3><ul><li>按你的弱点定制的热身，5分钟起（最长45分钟）</li><li>训练服务器：机器人重现你真实的阵亡和残局</li></ul></article>
 <article class="card"><span class="eyebrow">复盘</span><h3>一轮结束后</h3><ul><li>与之前的比赛相比有什么变化，以及原因</li><li>你本周的重点和值得尝试的测试</li><li>每场比赛逐回合回顾</li></ul></article>
</div>
<h2 id="see">看看效果</h2>
<div class="shots">
 <figure><video src="media/deaths.mp4" poster="media/deaths.jpg" autoplay muted loop playsinline preload="metadata"></video><figcaption><b>重现你自己的阵亡。</b>机器人会回到真实比赛中击杀你的确切位置（这里是Nuke第3回合，Hut Roof，你的路线为蓝色）：反复重打这场对枪，直到赢下来。</figcaption></figure>
 <figure><video src="media/live.mp4" poster="media/live.jpg" autoplay muted loop playsinline preload="metadata"></video><figcaption>第二块屏幕上的<b>实时页</b>，Nuke的一个回合（6倍速）：下包之后，然后是下一回合的计划，雷达上显示胜率、路线和道具。</figcaption></figure>
 <figure><video src="media/training.mp4" poster="media/training.jpg" autoplay muted loop playsinline preload="metadata"></video><figcaption><b>训练服务器</b>，Mirage上的道具练习：站在哪里、瞄哪里，以及道具是否及时落地。</figcaption></figure>
 <figure><img src="media/prepare.jpg" alt="准备页面：要练的地图、你最近输掉的回合、热身模块和你的等级" loading="lazy"><figcaption><b>准备</b>：热身从你最近丢回合的地方开始。</figcaption></figure>
</div>
<h2 id="how">使用方法</h2>
<ol class="steps">
 <li>打开<b>WilySetup.exe</b>，点击<b>Install</b>：它会下载我、校验每个部分，并为你的Windows账户安装（无需管理员权限）。我会随Windows启动，并在CS2启动时自动打开实时页。</li>
 <li>第一次启动时有三步：你的Steam账号（我会自动找到）、连接CS2（粘贴一个启动选项）、你的比赛历史记录验证码（无需创建Steam密钥）。之后你的比赛会在你的电脑上分析，每场几分钟。</li>
 <li>准备 → <b>热身</b>：训练服务器只会在你第一次打开时安装，并直接使用你的CS2游戏文件（链接方式：无需再次下载，不额外占用空间）。</li>
</ol>
<p class="note">需要Windows 10或11（64位）或Linux（Python 3.11+）、Steam上的CS2、一台8 GB内存的电脑（游戏和Wily一起使用），以及存放录像的磁盘空间（每场约250 MB）。应用支持中文、英语、法语、德语、俄语、葡萄牙语和西班牙语。</p>
<h2>公平竞技与隐私</h2>
<div class="grid">
 <article class="card"><h3>只用Valve提供的东西</h3><p>游戏状态集成（Game State Integration，游戏为HUD和RGB键盘提供的官方功能）、CS2写入的控制台日志、Steam Web API，以及你比赛的录像。我从不读取游戏内存或网络流量，也从不替你操作。训练服务器是只有你会加入的本地游戏副本。一切都可以核查：<a href="{C['github']}">代码是公开的</a>。</p></article>
 <article class="card"><h3>什么留在本地，什么会分享</h3><p>你的录像、档案、Steam验证码和语音永远不会离开你的电脑（如果你没有自己的Steam密钥，你的比赛列表会经由本网站转发给Steam，不做任何保存）。<b>默认分享、已匿名化：</b>我从你的新比赛中提取的数据表（位置、对枪、道具、购买、回合；每个SteamID都替换为随机ID，不含昵称和比赛ID），用于扩充数据库，以及匿名的使用计数。第一次启动时我会告诉你，一键即可同时关闭两者（之后也可在设置中关闭）。<a href="zh-privacy.html">隐私政策</a></p></article>
 <article class="card"><h3>免费alpha版</h3><p>测试期间免费。这是第一个向所有玩家开放的版本：通过我页面顶部的<b>alpha · report</b>标签（你能看到发送的内容）或邮件告诉我哪里出了问题。我的更新由作者签名，安装前我会先校验。问题或bug：<a href="mailto:{C['contact']}">{C['contact']}</a>。</p></article>
</div>
"""


def home_de(C, dl):
    return f"""
<h1>Hi, ich bin Wily.</h1>
<p class="lede">Dein CS2-Coach. Ich setze Bots genau dorthin, wo du in deinen echten Matches getötet wurdest, direkt in CS2, damit du das Duell wiederholst, bis du es gewinnst. Während deiner Matches gebe ich dir Live-Tipps auf deinem zweiten Bildschirm, und danach sage ich dir klar, was du korrigieren solltest. Ich lerne aus deinen Demos und aus einer Datenbank mit Tausenden von Matches. Kostenlose Open-Source-Alpha für Windows und Linux: die erste Version, die für alle offen ist, also rechne mit Ecken und Kanten.</p>
<section id="download">{dl}<p class="note"><b>Open Source</b> (Apache 2.0): Jede Zeile der App steht auf <a href="{C['github']}">GitHub</a>. Jede Version wird auch dort veröffentlicht, mit derselben SHA-256 wie auf dieser Seite und verknüpft mit dem genauen Commit, aus dem sie gebaut wurde: <a href="{C['github']}/releases">Versionen</a>.</p></section>
<div class="grid">
 <article class="card"><span class="eyebrow">Live</span><h3>Während des Matches</h3><ul><li>Was du diese Runde und die nächste kaufen solltest</li><li>Wohin die Ts wahrscheinlich gehen, aktualisiert mit der Uhr und dem, was du siehst</li><li>Deine Wege und deine starken Spots auf dem Radar, die Granaten, die sich jetzt lohnen</li></ul></article>
 <article class="card"><span class="eyebrow">Vorbereitung</span><h3>Vor dem Spielen</h3><ul><li>Ein Aufwärmen, aufgebaut auf deinen Schwächen, ab 5 Minuten (bis 45)</li><li>Ein Trainingsserver mit Bots, die deine echten Tode und Clutches nachspielen</li></ul></article>
 <article class="card"><span class="eyebrow">Auswertung</span><h3>Nach der Session</h3><ul><li>Was sich gegenüber deinen vorherigen Matches geändert hat, und warum</li><li>Dein Fokus der Woche und die Experimente zum Ausprobieren</li><li>Jedes Match Runde für Runde</li></ul></article>
</div>
<h2 id="see">So sieht es aus</h2>
<div class="shots">
 <figure><video src="media/deaths.mp4" poster="media/deaths.jpg" autoplay muted loop playsinline preload="metadata"></video><figcaption><b>Deine eigenen Tode, nachgespielt.</b> Die Bots kommen genau dorthin zurück, wo sie dich im echten Match getötet haben (hier Runde 3 auf Nuke, Hut Roof, dein Weg in Blau): Nimm das Duell noch einmal, bis du es gewinnst.</figcaption></figure>
 <figure><video src="media/live.mp4" poster="media/live.jpg" autoplay muted loop playsinline preload="metadata"></video><figcaption><b>Live</b> auf dem zweiten Bildschirm, eine Runde auf Nuke (6-fache Geschwindigkeit): nach dem Plant, dann der Plan der nächsten Runde mit ihren Chancen, den Wegen und den Granaten auf dem Radar.</figcaption></figure>
 <figure><video src="media/training.mp4" poster="media/training.jpg" autoplay muted loop playsinline preload="metadata"></video><figcaption><b>Trainingsserver</b>, eine Granatenübung auf Mirage: wo du stehst, wohin du zielst und ob sie rechtzeitig gelandet ist.</figcaption></figure>
 <figure><img src="media/prepare.jpg" alt="Die Seite Vorbereitung: Maps zum Trainieren, die Runden, die du in letzter Zeit verlierst, die Aufwärmblöcke und dein Level" loading="lazy"><figcaption><b>Vorbereitung</b>: Das Aufwärmen beginnt dort, wo du in letzter Zeit Runden verlierst.</figcaption></figure>
</div>
<h2 id="how">So funktioniert's</h2>
<ol class="steps">
 <li>Öffne <b>WilySetup.exe</b>, dann <b>Install</b>: Es lädt mich herunter, prüft jeden Teil und installiert mich für dein Windows-Konto (ohne Administratorrechte). Ich starte mit Windows und öffne Live von selbst, wenn CS2 startet.</li>
 <li>Beim ersten Start drei Schritte: dein Steam-Konto (ich finde es), CS2 verbinden (eine Startoption zum Einfügen), dein Verlaufscode für Matches (kein Steam-Schlüssel nötig). Danach werden deine Matches auf deinem PC analysiert, jedes in ein paar Minuten.</li>
 <li>Vorbereitung → <b>Aufwärmen</b>: Der Trainingsserver installiert sich erst, wenn du ihn zum ersten Mal öffnest, und läuft mit den Dateien deines CS2 (Verknüpfungen: kein zweiter Download, kein zusätzlicher Platz).</li>
</ol>
<p class="note">Du brauchst Windows 10 oder 11 (64 Bit) oder Linux (Python 3.11+), CS2 auf Steam, einen PC mit 8 GB RAM (für das Spiel und Wily zusammen) und Platz für deine Demos (etwa 250 MB pro Match). Die App spricht Deutsch, Englisch, Französisch, Russisch, Portugiesisch, Spanisch und Chinesisch.</p>
<h2>Fair Play und Datenschutz</h2>
<div class="grid">
 <article class="card"><h3>Nur, was Valve bereitstellt</h3><p>Game State Integration (die offizielle Funktion des Spiels für HUDs und RGB-Tastaturen), das Konsolen-Log, das CS2 schreibt, die Steam Web API und die Demos deiner Matches. Ich lese nie den Speicher oder den Netzwerkverkehr des Spiels und spiele nie für dich. Der Trainingsserver ist eine lokale Kopie des Spiels, der nur du beitrittst. Du kannst alles nachprüfen: <a href="{C['github']}">der Code ist öffentlich</a>.</p></article>
 <article class="card"><h3>Was hier bleibt, was geteilt wird</h3><p>Deine Demos, dein Profil, deine Steam-Codes und deine Stimme verlassen nie deinen PC (ohne eigenen Steam-Schlüssel geht deine Match-Liste über diese Website zu Steam, nichts wird gespeichert). <b>Standardmäßig geteilt, anonymisiert:</b> die Tabellen, die ich aus deinen neuen Matches extrahiere (Positionen, Duelle, Granaten, Käufe, Runden; jede SteamID durch eine zufällige ID ersetzt, keine Namen, keine Match-ID), um die Datenbank wachsen zu lassen, und anonyme Nutzungszähler. Beim ersten Start sage ich es dir, und ein Klick schaltet beides aus (oder später in den Einstellungen). <a href="de-privacy.html">Datenschutzerklärung</a></p></article>
 <article class="card"><h3>Kostenlose Alpha</h3><p>Kostenlos, solange getestet wird. Es ist die erste Version, die für alle Spieler offen ist: Sag mir, was kaputtgeht, über den Tag <b>alpha · melden</b> oben auf meiner Seite (du siehst, was gesendet wird) oder per E-Mail. Meine Updates sind von meinem Autor signiert, und ich prüfe sie, bevor ich etwas installiere. Fragen oder Bugs: <a href="mailto:{C['contact']}">{C['contact']}</a>.</p></article>
</div>
"""


HOME = {"de": home_de, "ru": home_ru, "pt": home_pt, "es": home_es, "zh": home_zh}


def privacy_ru(C):
    return f"""<div class="doc"><h1>Политика конфиденциальности</h1><p class="note">Последнее обновление: {UPDATED['ru']} · {PREVAILS['ru']} <a href="confidentialite.html" hreflang="fr">Версия на французском</a></p>
<p><b>Кто мы.</b> Wily — бесплатное приложение, издатель — {C['publisher']} (Франция), контакт: <a href="mailto:{C['contact']}">{C['contact']}</a>. Этот сайт размещён у Infomaniak Network SA (Швейцария).</p>
<p><b>Коротко.</b> Приложение работает на твоём ПК: твои матчи, профиль, записи голоса и коды Steam остаются там (без собственного ключа Steam приложение получает список твоих матчей через этот сайт, который ничего не сохраняет: см. п. 6). Учётных записей нет. На этот сайт попадают: проверки обновлений приложения, анонимные счётчики использования (их можно выключить), сообщения об ошибках, которые ты сам решаешь отправить, и твои матчи в обезличенном виде (отправка включена по умолчанию, её можно выключить). Сайт не ставит cookie, на нём нет аналитики, рекламы и отслеживания.</p>
<h2>1. Этот сайт</h2>
<p>Когда ты заходишь на него или скачиваешь приложение, серверы хостинга записывают технические журналы (IP-адрес, дата и время, запрошенная страница или файл, браузер) для безопасности и работы сайта. Хостинг хранит их ограниченное время; мы не используем их ни для чего другого. Сайт ничего не загружает с других серверов.</p>
<h2>2. Проверка обновлений</h2>
<p>Приложение скачивает <code>releases/latest.json</code> с этого сайта при запуске и раз в несколько часов, а файлы обновления — когда ты решаешь их установить. В этих запросах нет идентификаторов; как и любой веб-запрос, они показывают хостингу твой IP-адрес (см. п. 1).</p>
<h2>3. Отправка твоих матчей (включена по умолчанию, можно выключить)</h2>
<p>Если ты её не выключишь (в уведомлении при первом запуске или в любой момент: Настройки → <i>Делиться моими матчами с базой</i>), приложение после того, как ты увидел это уведомление, отправляет для каждого нового матча, проанализированного на твоём ПК, таблицы, извлечённые из демки (позиции игроков каждые полсекунды, дуэли, гранаты, закупки, раунды), предварительно обезличив их на твоём ПК:</p>
<ul><li>каждый SteamID заменяется идентификатором, полученным со случайным ключом, который используется только для этого матча и никогда не сохраняется: никто, включая нас, не может связать его с аккаунтом или связать игрока между двумя матчами;</li>
<li>все ники игроков удаляются;</li><li>идентификатор матча Valve заменяется случайным числом.</li></ul>
<p>Вместе с ними: случайный идентификатор твоей установки (создаётся приложением, не связан с твоим аккаунтом Steam), версия и сборка приложения, версия уведомления первого запуска, которое ты видел, карта каждого матча и отпечаток его раундов (матч, отправленный дважды, хранится один раз). Никогда — твои демки, голос, настройки, ключи, профиль или имя.</p>
<ul><li><b>Цель:</b> улучшать эталонную базу, с которой приложение сравнивает игроков.</li>
<li><b>Правовое основание:</b> наш законный интерес в улучшении приложения на обезличенных данных (ст. 6(1)(f) GDPR): отправленное нельзя связать ни с тобой, ни с другими игроками. <b>Ты можешь возразить в любой момент</b>, выключив эту опцию: больше ничего не отправляется.</li>
<li><b>На сервере:</b> скрипт приёма не сохраняет твой IP-адрес. Он хранит не более двух дней его хеш с ежедневной «солью», чтобы ограничить число отправок в день. Файлы ждут на хостинге, пока компьютер издателя их не заберёт (обычно в течение часа), после чего удаляются с хостинга.</li>
<li><b>В базе:</b> матчи становятся анонимными данными. Их нельзя связать ни с тобой, ни с другими игроками, и они хранятся, пока существует база.</li>
<li><b>До этого:</b> ты можешь попросить нас удалить то, что отправила твоя установка, указав её идентификатор (Настройки → Делиться моими матчами с базой).</li></ul>
<h2>4. Сообщения об ошибках и отзывы (только когда ты их отправляешь)</h2>
<p>Кнопка <i>alpha · report</i> в приложении отправляет то, что ты написал, твой e-mail, только если ты его указал (чтобы ответить), версию приложения, идентификатор твоей установки и, если оставить флажок, технические сведения: версии, версию Windows, страницу, на которой ты был, и её последние ошибки, а также конец журнала приложения, из которого удалены SteamID, адреса e-mail, известные приложению игровые ники и твоё имя пользователя Windows. Ты видишь всё это до отправки. Короткий вопрос «как прошло?» после разминки или матча отправляет, только если ты нажмёшь «Отправить», выбранные тобой смайлик, метки и слова вместе с тем, к чему они относятся (счёт разминки или карта и счёт матча). Команда <i>!report</i> на сервере тренировок отправляет то, что ты напишешь, с текущим упражнением и твоей позицией на карте.</p>
<ul><li><b>Цель:</b> исправлять и улучшать приложение. <b>Правовое основание:</b> твоё согласие, выраженное отправкой.</li>
<li><b>Хранение:</b> сообщение ждёт на хостинге, пока компьютер издателя его не заберёт (обычно в течение часа), затем удаляется там; издатель хранит его до решения проблемы, но не дольше одного года.</li>
<li>Чтобы удалить сообщение или узнать, что мы храним, напиши нам.</li></ul>
<h2>5. Анонимная статистика использования (можно выключить)</h2>
<p>Чтобы понимать, какие части приложения используются, а какие нет, и дорабатывать его на этой основе, приложение считает по дням: открытые страницы и время на каждой (только пока страница на экране), использованные кнопки (обозначенные страницей и элементом, никогда не тем, что на них написано), число ошибок страницы, время работы Live во время матча, а также версию приложения и класс размера экрана. Больше ничего: никаких идентификаторов (даже установки), SteamID, ников, ничего из того, что ты пишешь, никаких данных матчей.</p>
<ul><li>Завершившийся день отправляется на этот сайт и добавляется к итогам этого дня по всем игрокам, а сам отчёт удаляется: остаются только суммы по дням, которые нельзя связать ни с кем. Твой IP-адрес не сохраняется (см. п. 3 о ежедневном хеше с солью для ограничения отправок).</li>
<li><b>Правовое основание:</b> наш законный интерес в измерении использования приложения на условиях, которые CNIL устанавливает для измерения аудитории без согласия (только анонимная статистика, только для издателя). <b>Ты можешь возразить в любой момент</b>: Настройки → Статистика использования → Выключить; больше ничего не считается и не отправляется. Приложение сообщает об этом при первом открытии.</li>
<li><b>Хранение:</b> итоги по дням — не более 25 месяцев; счётчики на твоём ПК — 30 дней.</li></ul>
<h2>6. Получение списка твоих матчей через этот сайт (если у тебя нет своего ключа Steam)</h2>
<p>Чтобы найти твои новые матчи, приложение запрашивает у Steam Web API от Valve следующий матч твоей истории. Для этого нужен ключ Steam Web API: если ты добавил свой в приложении, оно обращается к Valve напрямую. Если нет, оно отправляет этому сайту в теле зашифрованного запроса твой SteamID, код истории матчей и код последнего известного ему матча; сайт передаёт их Valve со своим ключом и возвращает ответ Valve. Так же приложение может запрашивать публичные имена Steam для SteamID и публичный список друзей (чтобы распознать твою группу).</p>
<ul><li><b>Ничего не сохраняется:</b> коды используются только для этого запроса и никогда не записываются сайтом ни в файл, ни в журнал. Объём ограничивает только счётчик по дням (твой адрес в виде хеша с солью дня, удаляется через два дня, см. п. 3).</li>
<li><b>Правовое основание:</b> исполнение услуги, которую ты запрашиваешь (ст. 6(1)(b) GDPR). Чтобы полностью этого избежать, добавь свой ключ в Настройках.</li></ul>
<h2>7. Что приложение делает на твоём ПК (нам не отправляется)</h2>
<ul><li><b>Код истории матчей (и твой собственный ключ Steam Web API, если ты его добавил):</b> хранятся в <code>out/settings.json</code> на твоём ПК и отправляются в Steam Web API от Valve для получения списка матчей — напрямую с твоим ключом или через этот сайт (см. п. 6).</li>
<li><b>Демки твоих матчей</b> (скачанные с серверов Valve через твой клиент Steam) и то, что приложение из них извлекает, включая других игроков твоих матчей (их SteamID и игровые ники, как в любой демке): обрабатываются на твоём ПК, чтобы тебя тренировать, и хранятся на твоём ПК.</li>
<li><b>Голос (по желанию, выключен по умолчанию):</b> приложение может записывать твой микрофон во время матчей и расшифровывать запись на твоём ПК. Запись тиммейтов (звукового выхода твоего ПК) требует их согласия в каждом матче; приложение включает её только после твоего подтверждения в игре. Записи никогда не покидают твой ПК.</li>
<li><b>Сервисы, к которым приложение обращается с твоего ПК</b>, когда ты пользуешься соответствующей функцией, по их собственным политикам: Valve (Steam Web API, Steam Community, игровой координатор через твой клиент Steam, серверы демок), публичный API Leetify (статистика игроков, которых ты анализируешь), GitHub (радары карт, сборник лайнапов), Hugging Face (модель распознавания речи, если ты пользуешься голосом).</li></ul>
<h2>8. База, поставляемая с приложением</h2>
<p>Приложение содержит эталонные таблицы, рассчитанные по демкам матчмейкинга Counter-Strike 2. У каждого игрока в них выдуманный идентификатор и нет ника. Профессиональные матчи (из публичных демок, опубликованных HLTV.org) сохраняют публичные имена игроков; если ты один из них и хочешь удалить какие-то данные, свяжись с нами.</p>
<h2>9. Твои права</h2>
<p>По GDPR ты имеешь право на доступ к своим персональным данным, их исправление и удаление, на ограничение обработки и возражение против неё, на переносимость данных и на отзыв согласия. Контакт: <a href="mailto:{C['contact']}">{C['contact']}</a>. Ты также можешь подать жалобу в CNIL (<a href="https://www.cnil.fr">www.cnil.fr</a>) или в надзорный орган своей страны.</p>
<h2>10. Где находятся данные</h2>
<p>Хостинг находится в Швейцарии, которую Европейская комиссия признаёт страной с достаточным уровнем защиты. Компьютер издателя находится во Франции.</p>
<h2>11. Изменения</h2><p>Эта страница меняется, когда меняется использование данных приложением; дата вверху — дата последнего обновления.</p></div>"""


def privacy_pt(C):
    return f"""<div class="doc"><h1>Política de privacidade</h1><p class="note">Última atualização: {UPDATED['pt']} · {PREVAILS['pt']} <a href="confidentialite.html" hreflang="fr">Versão em francês</a></p>
<p><b>Quem somos.</b> O Wily é um app gratuito publicado por {C['publisher']} (França), contato: <a href="mailto:{C['contact']}">{C['contact']}</a>. Este site é hospedado pela Infomaniak Network SA (Suíça).</p>
<p><b>Em resumo.</b> O app roda no seu PC: suas partidas, seu perfil, suas gravações de voz e seus códigos da Steam ficam lá (sem uma chave da Steam sua, o app lista suas partidas por este site, que não guarda nada: veja o item 6). Não há contas. O que chega a este site: as verificações de atualização do app, contadores de uso anônimos (você pode desligar), os relatos de bug que você decide enviar e suas partidas, anonimizadas (compartilhadas por padrão, você pode desligar). Este site não usa cookies e não tem análise de visitas, publicidade nem rastreamento.</p>
<h2>1. Este site</h2>
<p>Quando você o visita ou baixa o app, os servidores da hospedagem registram logs técnicos (endereço IP, data e hora, página ou arquivo pedido, navegador) para segurança e funcionamento. A hospedagem os guarda por tempo limitado; não os usamos para mais nada. O site não carrega nada de outros servidores.</p>
<h2>2. Verificações de atualização</h2>
<p>O app baixa <code>releases/latest.json</code> deste site ao iniciar e a cada poucas horas, e os arquivos de atualização quando você escolhe instalá-los. Essas requisições não levam nenhum identificador; como qualquer requisição web, mostram seu endereço IP à hospedagem (veja o item 1).</p>
<h2>3. Compartilhamento das suas partidas (ligado por padrão, você pode desligar)</h2>
<p>A menos que você desligue (no aviso mostrado na primeira vez, ou a qualquer momento em Configurações → <i>Compartilhar minhas partidas com a base</i>), o app envia, depois que você viu esse aviso, para cada partida nova analisada no seu PC, as tabelas extraídas da demo (posições dos jogadores a cada meio segundo, duelos, granadas, compras, rounds), depois de anonimizá-las no seu PC:</p>
<ul><li>cada SteamID é substituído por um identificador gerado com uma chave aleatória usada só para aquela partida e nunca guardada: ninguém, nem nós, consegue voltar a uma conta nem ligar um jogador entre duas partidas;</li>
<li>todos os nomes de jogadores são removidos;</li><li>o identificador da partida na Valve é substituído por um número aleatório.</li></ul>
<p>Junto com elas: um identificador aleatório da sua instalação (criado pelo app, sem ligação com sua conta Steam), a versão e o build do app, a versão do aviso da primeira vez que você viu, o mapa de cada partida e uma impressão digital dos rounds dela (uma partida compartilhada duas vezes é guardada uma vez só). Nunca suas demos, sua voz, suas configurações, suas chaves, seu perfil ou seu nome.</p>
<ul><li><b>Finalidade:</b> melhorar a base de referência com a qual o app compara os jogadores.</li>
<li><b>Base legal:</b> nosso interesse legítimo em melhorar o app com dados anonimizados (artigo 6(1)(f) do RGPD): o que é enviado não pode ser ligado a você nem aos outros jogadores. <b>Você pode se opor a qualquer momento</b> desligando a opção: nada mais é enviado.</li>
<li><b>No servidor:</b> o script de recebimento não guarda seu endereço IP. Ele mantém, por no máximo dois dias, um hash dele com um sal diário, para limitar os envios por dia. Os arquivos esperam na hospedagem até o computador do editor buscá-los (normalmente em até uma hora) e depois são apagados da hospedagem.</li>
<li><b>Na base:</b> as partidas passam a ser dados anônimos. Não podem ser ligadas a você nem aos outros jogadores, e são guardadas enquanto a base existir.</li>
<li><b>Antes disso:</b> você pode nos pedir para apagar o que sua instalação enviou, com o identificador da instalação (Configurações → Compartilhar minhas partidas com a base).</li></ul>
<h2>4. Relatos de bug e opiniões (só quando você envia)</h2>
<p>O botão <i>alpha · report</i> do app envia o que você escreve, seu e-mail só se você informar (para te responder), a versão do app, o identificador da sua instalação e, se você deixar a caixa marcada, detalhes técnicos: versões, versão do Windows, a página em que você estava e os últimos erros dela, e o final do log do app, do qual são removidos SteamIDs, endereços de e-mail, nomes de jogo que ele conhece e seu nome de usuário do Windows. Você vê tudo antes de enviar. O curto "como foi?" depois de um aquecimento ou de uma partida envia, só se você clicar em Enviar, a carinha, as etiquetas e as palavras que você escolheu, com o assunto (a pontuação do aquecimento, ou o mapa e o placar da partida). O comando <i>!report</i> do servidor de treino envia o que você digita, com o exercício em que você estava e onde você estava no mapa.</p>
<ul><li><b>Finalidade:</b> corrigir e melhorar o app. <b>Base legal:</b> seu consentimento, dado ao enviar.</li>
<li><b>Guarda:</b> o relato espera na hospedagem até o computador do editor buscá-lo (normalmente em até uma hora) e então é apagado de lá; o editor o guarda até o problema ser resolvido, no máximo um ano.</li>
<li>Para apagar um relato ou saber o que guardamos: escreva para nós.</li></ul>
<h2>5. Estatísticas de uso anônimas (você pode desligar)</h2>
<p>Para saber quais partes do app são usadas e quais não, e retrabalhá-lo com base nisso, o app conta, por dia: as páginas abertas e o tempo passado em cada uma (só enquanto a página está na tela), os botões usados (identificados pela página e pelo elemento, nunca pelo que está escrito neles), o número de erros que a página encontra, o tempo em que o Ao vivo roda durante uma partida, além da versão do app e de uma classe de tamanho de tela. Nada mais: nenhum identificador (nem o da instalação), nenhum SteamID, nenhum nome, nada do que você escreve, nenhum dado de partida.</p>
<ul><li>Um dia já encerrado é enviado a este site, somado aos totais daquele dia de todos os jogadores, e o relatório em si é descartado: só ficam somas por dia, que não podem ser ligadas a ninguém. Seu endereço IP não é guardado (veja o item 3 sobre o hash diário com sal usado para limitar os envios).</li>
<li><b>Base legal:</b> nosso interesse legítimo em medir o uso do app, nas condições que a CNIL define para a medição de audiência isenta de consentimento (só estatísticas anônimas, só para o editor). <b>Você pode se opor a qualquer momento</b>: Configurações → Estatísticas de uso → Desligar; nada mais é contado nem enviado. O app te avisa disso na primeira vez que abre.</li>
<li><b>Guarda:</b> os totais por dia, no máximo 25 meses; os contadores guardados no seu PC, 30 dias.</li></ul>
<h2>6. A lista das suas partidas por este site (quando você não tem uma chave da Steam sua)</h2>
<p>Para achar suas partidas novas, o app pede à Steam Web API da Valve a próxima partida do seu histórico. Isso precisa de uma chave da Steam Web API: se você adicionou a sua no app, ele fala direto com a Valve. Se não, ele envia a este site, no corpo de uma requisição criptografada, seu SteamID, seu código de histórico de partidas e o código da última partida que ele conhece; o site repassa isso à Valve com a chave dele e devolve a resposta da Valve. Do mesmo jeito, o app pode pedir os nomes públicos da Steam de SteamIDs e uma lista de amigos pública (para reconhecer seu grupo).</p>
<ul><li><b>Nada é guardado:</b> os códigos servem só para aquela requisição e nunca são gravados pelo site em arquivo ou log. Só um contador por dia limita o volume (seu endereço como hash com o sal do dia, apagado depois de dois dias, veja o item 3).</li>
<li><b>Base legal:</b> a execução do serviço que você pede (artigo 6(1)(b) do RGPD). Para evitar isso totalmente, adicione sua própria chave nas Configurações.</li></ul>
<h2>7. O que o app faz no seu PC (não é enviado para nós)</h2>
<ul><li><b>Código de histórico de partidas (e sua própria chave da Steam Web API, se você adicionar uma):</b> guardados em <code>out/settings.json</code> no seu PC, enviados à Steam Web API da Valve para listar suas partidas, direto com sua chave ou por este site (veja o item 6).</li>
<li><b>As demos das suas partidas</b> (baixadas dos servidores da Valve pelo seu cliente Steam) e o que o app extrai delas, incluindo os outros jogadores das suas partidas (os SteamIDs e nomes de jogo deles, como em qualquer demo): processados no seu PC para te treinar e guardados no seu PC.</li>
<li><b>Voz (opcional, desligada por padrão):</b> o app pode gravar seu microfone durante as partidas e transcrevê-lo no seu PC. Gravar seus aliados (a saída de som do seu PC) exige o acordo deles em cada partida; o app só começa depois que você confirma no jogo. As gravações nunca saem do seu PC.</li>
<li><b>Serviços que o app contata a partir do seu PC</b> quando você usa o recurso relacionado, sob as políticas deles: Valve (Steam Web API, Steam Community, o coordenador do jogo pelo seu cliente Steam, servidores de demos), a API pública do Leetify (estatísticas dos jogadores que você analisa), GitHub (radares dos mapas, um livro de lineups), Hugging Face (o modelo de reconhecimento de voz, se você usar voz).</li></ul>
<h2>8. A base que vem com o app</h2>
<p>O app traz tabelas de referência calculadas a partir de demos de matchmaking do Counter-Strike 2. Cada jogador nelas tem um identificador inventado e nenhum nome. As partidas profissionais (de demos públicas publicadas pela HLTV.org) mantêm os nomes públicos dos jogadores; se você é um deles e quer que um dado seja removido, fale conosco.</p>
<h2>9. Seus direitos</h2>
<p>Pelo RGPD você tem direito de acesso, retificação e apagamento dos seus dados pessoais, de limitação e de oposição ao tratamento, de portabilidade e de retirar seu consentimento. Contato: <a href="mailto:{C['contact']}">{C['contact']}</a>. Você também pode apresentar uma reclamação à CNIL (<a href="https://www.cnil.fr">www.cnil.fr</a>) ou à autoridade de proteção de dados do seu país (no Brasil, a ANPD).</p>
<h2>10. Onde ficam os dados</h2>
<p>A hospedagem fica na Suíça, que a Comissão Europeia reconhece como país com proteção adequada. O computador do editor fica na França.</p>
<h2>11. Mudanças</h2><p>Esta página muda quando o uso de dados pelo app muda; a data no topo é a da última atualização.</p></div>"""


def privacy_es(C):
    return f"""<div class="doc"><h1>Política de privacidad</h1><p class="note">Última actualización: {UPDATED['es']} · {PREVAILS['es']} <a href="confidentialite.html" hreflang="fr">Versión en francés</a></p>
<p><b>Quiénes somos.</b> Wily es una app gratuita publicada por {C['publisher']} (Francia), contacto: <a href="mailto:{C['contact']}">{C['contact']}</a>. Este sitio está alojado por Infomaniak Network SA (Suiza).</p>
<p><b>En resumen.</b> La app funciona en tu PC: tus partidas, tu perfil, tus grabaciones de voz y tus códigos de Steam se quedan ahí (sin una clave de Steam propia, la app lista tus partidas a través de este sitio, que no guarda nada: ver punto 6). No hay cuentas. Lo que llega a este sitio: las comprobaciones de actualización de la app, contadores de uso anónimos (puedes desactivarlos), los reportes de errores que decides enviar y tus partidas, anonimizadas (compartidas por defecto, puedes desactivarlo). Este sitio no usa cookies y no tiene analítica, publicidad ni rastreo.</p>
<h2>1. Este sitio</h2>
<p>Cuando lo visitas o descargas la app, los servidores del alojamiento registran logs técnicos (dirección IP, fecha y hora, página o archivo pedido, navegador) por seguridad y funcionamiento. El alojamiento los conserva un tiempo limitado; no los usamos para nada más. El sitio no carga nada de otros servidores.</p>
<h2>2. Comprobaciones de actualización</h2>
<p>La app descarga <code>releases/latest.json</code> de este sitio al iniciar y cada pocas horas, y los archivos de actualización cuando eliges instalarlos. Estas solicitudes no llevan ningún identificador; como cualquier solicitud web, muestran tu dirección IP al alojamiento (ver punto 1).</p>
<h2>3. Compartir tus partidas (activado por defecto, puedes desactivarlo)</h2>
<p>Salvo que lo desactives (en el aviso que aparece la primera vez, o en cualquier momento en Ajustes → <i>Compartir mis partidas con la base</i>), la app envía, una vez que viste ese aviso, por cada partida nueva analizada en tu PC, las tablas que extrajo de la demo (posiciones de los jugadores cada medio segundo, duelos, granadas, compras, rondas), después de anonimizarlas en tu PC:</p>
<ul><li>cada SteamID se reemplaza por un identificador generado con una clave aleatoria usada solo para esa partida y nunca guardada: nadie, ni siquiera nosotros, puede vincularlo con una cuenta ni relacionar a un jugador entre dos partidas;</li>
<li>se eliminan todos los nombres de jugadores;</li><li>el identificador de la partida de Valve se reemplaza por un número aleatorio.</li></ul>
<p>Junto con ellas: un identificador aleatorio de tu instalación (creado por la app, sin vínculo con tu cuenta de Steam), la versión y el build de la app, la versión del aviso de primera vez que viste, el mapa de cada partida y una huella de sus rondas (una partida compartida dos veces se guarda una sola vez). Nunca tus demos, tu voz, tus ajustes, tus claves, tu perfil ni tu nombre.</p>
<ul><li><b>Finalidad:</b> mejorar la base de referencia con la que la app compara a los jugadores.</li>
<li><b>Base legal:</b> nuestro interés legítimo en mejorar la app con datos anonimizados (artículo 6(1)(f) del RGPD): lo que se envía no puede vincularse contigo ni con los demás jugadores. <b>Puedes oponerte en cualquier momento</b> desactivando la opción: no se envía nada más.</li>
<li><b>En el servidor:</b> el script de recepción no guarda tu dirección IP. Conserva, como máximo dos días, un hash de ella con una sal diaria, para limitar los envíos por día. Los archivos esperan en el alojamiento hasta que la computadora del editor los recupera (normalmente en menos de una hora) y luego se borran del alojamiento.</li>
<li><b>En la base:</b> las partidas pasan a ser datos anónimos. No pueden vincularse contigo ni con los demás jugadores, y se conservan mientras exista la base.</li>
<li><b>Antes de eso:</b> puedes pedirnos que borremos lo que envió tu instalación, con su identificador (Ajustes → Compartir mis partidas con la base).</li></ul>
<h2>4. Reportes de errores y opiniones (solo cuando los envías)</h2>
<p>El botón <i>alpha · report</i> de la app envía lo que escribes, tu correo solo si lo das (para responderte), la versión de la app, el identificador de tu instalación y, si dejas la casilla marcada, detalles técnicos: versiones, versión de Windows, la página en la que estabas y sus últimos errores, y el final del log de la app, del que se quitan los SteamID, las direcciones de correo, los nombres de juego que conoce y tu nombre de usuario de Windows. Ves todo antes de enviar. El breve "¿qué tal fue?" después de un calentamiento o una partida envía, solo si presionas Enviar, la carita, las etiquetas y las palabras que elegiste, con aquello a lo que se refiere (el puntaje del calentamiento, o el mapa y el marcador de la partida). El comando <i>!report</i> del servidor de entrenamiento envía lo que escribes con el ejercicio en el que estabas y dónde estabas en el mapa.</p>
<ul><li><b>Finalidad:</b> corregir y mejorar la app. <b>Base legal:</b> tu consentimiento, dado al enviar.</li>
<li><b>Conservación:</b> el reporte espera en el alojamiento hasta que la computadora del editor lo recupera (normalmente en menos de una hora) y luego se borra ahí; el editor lo conserva hasta que el problema se resuelve, como máximo un año.</li>
<li>Para borrar un reporte o saber qué guardamos: escríbenos.</li></ul>
<h2>5. Estadísticas de uso anónimas (puedes desactivarlas)</h2>
<p>Para saber qué partes de la app se usan y cuáles no, y rehacerla sobre esa base, la app cuenta, por día: las páginas abiertas y el tiempo pasado en cada una (solo mientras la página está en pantalla), los botones usados (identificados por la página y el elemento, nunca por lo que dicen), el número de errores que encuentra la página, el tiempo que En vivo funciona durante una partida, además de la versión de la app y una clase de tamaño de pantalla. Nada más: ningún identificador (ni siquiera el de la instalación), ningún SteamID, ningún nombre, nada de lo que escribes, ningún dato de partida.</p>
<ul><li>Un día ya terminado se envía a este sitio, se suma a los totales de ese día de todos los jugadores, y el reporte en sí se descarta: solo quedan sumas por día, que no pueden vincularse con nadie. Tu dirección IP no se guarda (ver punto 3 sobre el hash diario con sal usado para limitar los envíos).</li>
<li><b>Base legal:</b> nuestro interés legítimo en medir el uso de la app, en las condiciones que fija la CNIL para la medición de audiencia exenta de consentimiento (solo estadísticas anónimas, solo para el editor). <b>Puedes oponerte en cualquier momento</b>: Ajustes → Estadísticas de uso → Desactivar; no se cuenta ni se envía nada más. La app te lo dice la primera vez que se abre.</li>
<li><b>Conservación:</b> los totales por día, como máximo 25 meses; los contadores guardados en tu PC, 30 días.</li></ul>
<h2>6. Listar tus partidas a través de este sitio (cuando no tienes una clave de Steam propia)</h2>
<p>Para encontrar tus partidas nuevas, la app le pide a la Steam Web API de Valve la siguiente partida de tu historial. Para eso hace falta una clave de Steam Web API: si agregaste la tuya en la app, la app le pregunta directamente a Valve. Si no, envía a este sitio, en el cuerpo de una solicitud cifrada, tu SteamID, tu código de historial de partidas y el código de la última partida que conoce; el sitio se los pasa a Valve con su propia clave y devuelve la respuesta de Valve. Del mismo modo, la app puede pedir los nombres públicos de Steam de SteamIDs y una lista de amigos pública (para reconocer a tu grupo).</p>
<ul><li><b>No se guarda nada:</b> los códigos se usan solo para esa solicitud y el sitio nunca los escribe en un archivo ni en un log. Solo un contador por día limita el volumen (tu dirección como hash con la sal del día, borrado después de dos días, ver punto 3).</li>
<li><b>Base legal:</b> la ejecución del servicio que pides (artículo 6(1)(b) del RGPD). Para evitarlo por completo, agrega tu propia clave en Ajustes.</li></ul>
<h2>7. Lo que la app hace en tu PC (no se nos envía)</h2>
<ul><li><b>Código de historial de partidas (y tu propia clave de Steam Web API, si agregas una):</b> guardados en <code>out/settings.json</code> en tu PC, enviados a la Steam Web API de Valve para listar tus partidas, directamente con tu clave o a través de este sitio (ver punto 6).</li>
<li><b>Las demos de tus partidas</b> (descargadas de los servidores de Valve a través de tu cliente de Steam) y lo que la app extrae de ellas, incluidos los demás jugadores de tus partidas (sus SteamID y nombres de juego, como en cualquier demo): procesados en tu PC para entrenarte, guardados en tu PC.</li>
<li><b>Voz (opcional, desactivada por defecto):</b> la app puede grabar tu micrófono durante las partidas y transcribirlo en tu PC. Grabar a tus compañeros (la salida de sonido de tu PC) necesita su acuerdo en cada partida; la app solo la inicia después de que lo confirmas en el juego. Las grabaciones nunca salen de tu PC.</li>
<li><b>Servicios que la app contacta desde tu PC</b> cuando usas la función relacionada, bajo sus propias políticas: Valve (Steam Web API, Steam Community, el coordinador del juego a través de tu cliente de Steam, servidores de demos), la API pública de Leetify (estadísticas de los jugadores que analizas), GitHub (radares de los mapas, un libro de lineups), Hugging Face (el modelo de reconocimiento de voz, si usas la voz).</li></ul>
<h2>8. La base que viene con la app</h2>
<p>La app incluye tablas de referencia calculadas a partir de demos de matchmaking de Counter-Strike 2. Cada jugador en ellas tiene un identificador inventado y ningún nombre. Las partidas profesionales (de demos públicas publicadas por HLTV.org) conservan los nombres públicos de los jugadores; si eres uno de ellos y quieres que se quite un dato, contáctanos.</p>
<h2>9. Tus derechos</h2>
<p>Según el RGPD tienes derecho de acceso, rectificación y supresión de tus datos personales, de limitación y oposición a su tratamiento, de portabilidad y de retirar tu consentimiento. Contacto: <a href="mailto:{C['contact']}">{C['contact']}</a>. También puedes presentar un reclamo ante la CNIL (<a href="https://www.cnil.fr">www.cnil.fr</a>) o ante la autoridad de protección de datos de tu país.</p>
<h2>10. Dónde están los datos</h2>
<p>El alojamiento está en Suiza, país que la Comisión Europea reconoce como de protección adecuada. La computadora del editor está en Francia.</p>
<h2>11. Cambios</h2><p>Esta página cambia cuando cambia el uso de los datos por parte de la app; la fecha de arriba es la de la última actualización.</p></div>"""


def privacy_zh(C):
    return f"""<div class="doc"><h1>隐私政策</h1><p class="note">最后更新：{UPDATED['zh']} · {PREVAILS['zh']}<a href="confidentialite.html" hreflang="fr">法文版本</a></p>
<p><b>我们是谁。</b>Wily是由{C['publisher']}（法国）发布的免费应用，联系方式：<a href="mailto:{C['contact']}">{C['contact']}</a>。本网站由Infomaniak Network SA（瑞士）托管。</p>
<p><b>简而言之。</b>应用在你的电脑上运行：你的比赛、档案、语音录音和Steam验证码都保存在那里（如果你没有自己的Steam密钥，应用会经由本网站获取你的比赛列表，本网站不保存任何内容：见第6条）。没有账号。会到达本网站的内容：应用的更新检查、匿名使用计数（可以关闭）、你选择发送的错误报告，以及经过匿名化的比赛数据（默认分享，可以关闭）。本网站不设置cookie，也没有访问统计、广告或追踪。</p>
<h2>1. 本网站</h2>
<p>当你访问本网站或下载应用时，托管服务商的服务器会出于安全和运行目的记录技术日志（IP地址、日期和时间、请求的页面或文件、浏览器）。托管服务商在有限时间内保存这些日志；我们不将其用于其他任何目的。本网站不从其他服务器加载任何内容。</p>
<h2>2. 更新检查</h2>
<p>应用会在启动时以及每隔几个小时从本网站下载<code>releases/latest.json</code>，并在你选择安装时下载更新文件。这些请求不带任何标识符；与任何网络请求一样，它们会向托管服务商显示你的IP地址（见第1条）。</p>
<h2>3. 分享你的比赛（默认开启，可以关闭）</h2>
<p>除非你关闭此功能（在首次启动时显示的通知中，或随时在 设置 → <i>把我的比赛分享到数据库</i> 中关闭），否则在你看过该通知后，应用会针对在你电脑上分析的每场新比赛，发送从录像中提取的数据表（每半秒一次的玩家位置、对枪、道具、购买、回合），发送前已在你的电脑上完成匿名化：</p>
<ul><li>每个SteamID都会被替换为一个标识符，该标识符使用仅用于这场比赛、且从不保存的随机密钥生成：任何人（包括我们）都无法将其追溯到某个账号，也无法在两场比赛之间关联同一名玩家；</li>
<li>所有玩家昵称都会被删除；</li><li>Valve的比赛标识符会被替换为一个随机数。</li></ul>
<p>随数据一同发送的有：你的安装的随机标识符（由应用生成，与你的Steam账号无关）、应用的版本和构建号、你看到的首次启动通知的版本、每场比赛的地图及其回合的指纹（同一场比赛分享两次只保留一次）。绝不包括你的录像、语音、设置、密钥、档案或姓名。</p>
<ul><li><b>目的：</b>改进应用用来对比玩家的参考数据库。</li>
<li><b>法律依据：</b>我们以匿名数据改进应用的正当利益（GDPR第6(1)(f)条）：发送的内容既无法与你关联，也无法与其他玩家关联。<b>你可以随时反对</b>，关闭该选项即可：之后不会再发送任何内容。</li>
<li><b>在服务器上：</b>接收脚本不保存你的IP地址。它最多保留两天你IP地址加每日盐值后的哈希，用于限制每天的发送次数。文件在托管服务器上等待，直到发布者的电脑将其取回（通常在一小时内），随后即从托管服务器上删除。</li>
<li><b>在数据库中：</b>这些比赛随后即为匿名数据，既无法与你关联，也无法与其他玩家关联，并在数据库存在期间一直保存。</li>
<li><b>在此之前：</b>你可以凭你的安装标识符，要求我们删除你的安装所发送的内容（设置 → 把我的比赛分享到数据库）。</li></ul>
<h2>4. 错误报告和反馈（仅在你发送时）</h2>
<p>应用中的<i>alpha · report</i>按钮会发送你写的内容、你的电子邮箱（仅在你提供时，以便回复你）、应用版本、你的安装标识符，以及在你保留勾选时的技术细节：各版本号、Windows版本、你当时所在的页面及其最近的错误，以及应用日志的末尾部分（其中的SteamID、电子邮箱地址、应用已知的游戏昵称和你的Windows用户名均已删除）。发送前你能看到全部内容。热身或比赛后简短的“感觉怎么样？”仅在你点击“发送”时，才会发送你选择的表情、标签和文字，以及相关内容（热身得分，或比赛的地图和比分）。训练服务器的<i>!report</i>命令会发送你输入的内容，以及你当时的练习和你在地图上的位置。</p>
<ul><li><b>目的：</b>修复和改进应用。<b>法律依据：</b>你的同意，以发送行为表示。</li>
<li><b>保存期限：</b>报告在托管服务器上等待，直到发布者的电脑将其取回（通常在一小时内），随后即在那里删除；发布者保存至问题解决为止，最长一年。</li>
<li>如需删除报告或了解我们保存了什么：请写信给我们。</li></ul>
<h2>5. 匿名使用统计（可以关闭）</h2>
<p>为了了解应用的哪些部分被使用、哪些没有，并据此改进，应用每天统计：打开的页面以及在每个页面上停留的时间（仅在页面显示时）、使用的按钮（以页面和元素标识，从不记录按钮上的文字）、页面遇到的错误数量、比赛中实时页运行的时间，以及应用版本和屏幕尺寸类别。仅此而已：没有任何标识符（连安装标识符也没有）、没有SteamID、没有昵称、没有你写的任何内容、没有比赛数据。</p>
<ul><li>一天结束后，数据会发送到本网站，加入当天所有玩家的总数，报告本身随即丢弃：只保留每天的总和，无法与任何人关联。不保存你的IP地址（关于用于限制发送的每日加盐哈希，见第3条）。</li>
<li><b>法律依据：</b>我们衡量应用使用情况的正当利益，符合CNIL对免于同意的受众测量所规定的条件（仅匿名统计，仅供发布者使用）。<b>你可以随时反对</b>：设置 → 使用统计 → 关闭；之后不会再统计或发送任何内容。应用在首次打开时会告诉你这一点。</li>
<li><b>保存期限：</b>每日总数最长25个月；保存在你电脑上的计数30天。</li></ul>
<h2>6. 经由本网站获取你的比赛列表（当你没有自己的Steam密钥时）</h2>
<p>为了找到你的新比赛，应用会向Valve的Steam Web API请求你历史记录中的下一场比赛。这需要一个Steam Web API密钥：如果你在应用中添加了自己的密钥，应用会直接向Valve请求。否则，应用会在一个加密请求的正文中，把你的SteamID、你的比赛历史记录验证码以及它已知的最后一场比赛的代码发送到本网站；本网站使用自己的密钥将其转发给Valve，并返回Valve的答复。同样，应用也可以请求SteamID对应的公开Steam名称和公开的好友列表（用于识别你的车队）。</p>
<ul><li><b>不保存任何内容：</b>这些代码仅用于该次请求，本网站从不将其写入文件或日志。只有每日计数用于限制请求量（你的地址加当日盐值后的哈希，两天后删除，见第3条）。</li>
<li><b>法律依据：</b>履行你所请求的服务（GDPR第6(1)(b)条）。如想完全避免，请在设置中添加你自己的密钥。</li></ul>
<h2>7. 应用在你电脑上做的事（不会发送给我们）</h2>
<ul><li><b>比赛历史记录验证码（以及你添加的自己的Steam Web API密钥）：</b>保存在你电脑上的<code>out/settings.json</code>中，发送给Valve的Steam Web API以列出你的比赛，可直接使用你的密钥，也可经由本网站（见第6条）。</li>
<li><b>你比赛的录像</b>（通过你的Steam客户端从Valve服务器下载）以及应用从中提取的内容，包括你比赛中的其他玩家（他们的SteamID和游戏昵称，与任何录像中一样）：在你的电脑上处理以指导你，并保存在你的电脑上。</li>
<li><b>语音（可选，默认关闭）：</b>应用可以在比赛中录制你的麦克风，并在你的电脑上转写。录制你的队友（你电脑的声音输出）需要他们在每场比赛中同意；应用只有在你于游戏中确认后才会开始录制。录音永远不会离开你的电脑。</li>
<li><b>应用从你电脑联系的服务</b>（在你使用相关功能时，适用其各自的隐私政策）：Valve（Steam Web API、Steam社区、通过你的Steam客户端连接的游戏协调服务器、录像服务器）、Leetify公开API（你所分析玩家的统计数据）、GitHub（地图雷达、一份道具投掷合集）、Hugging Face（语音识别模型，如果你使用语音功能）。</li></ul>
<h2>8. 随应用提供的数据库</h2>
<p>应用附带根据《反恐精英2》匹配录像计算出的参考数据表。其中每名玩家都使用虚构的标识符，没有昵称。职业比赛（来自HLTV.org发布的公开录像）保留了选手的公开名称；如果你是其中之一并希望删除某项数据，请联系我们。</p>
<h2>9. 你的权利</h2>
<p>根据GDPR，你享有访问、更正和删除个人数据的权利，限制和反对处理的权利，数据可携带权，以及撤回同意的权利。联系方式：<a href="mailto:{C['contact']}">{C['contact']}</a>。你也可以向CNIL（<a href="https://www.cnil.fr">www.cnil.fr</a>）或你所在国家的监管机构投诉。</p>
<h2>10. 数据存放在哪里</h2>
<p>托管服务商位于瑞士，欧盟委员会认可其提供充分的保护。发布者的电脑位于法国。</p>
<h2>11. 变更</h2><p>当应用对数据的使用发生变化时，本页面会随之更新；顶部的日期为最后更新日期。</p></div>"""


def privacy_de(C):
    return f"""<div class="doc"><h1>Datenschutzerklärung</h1><p class="note">Zuletzt aktualisiert: {UPDATED['de']} · {PREVAILS['de']} <a href="confidentialite.html" hreflang="fr">Französische Fassung</a></p>
<p><b>Wer wir sind.</b> Wily ist eine kostenlose App, herausgegeben von {C['publisher']} (Frankreich), Kontakt: <a href="mailto:{C['contact']}">{C['contact']}</a>. Diese Website wird von der Infomaniak Network SA (Schweiz) gehostet.</p>
<p><b>Kurz gesagt.</b> Die App läuft auf deinem PC: Deine Matches, dein Profil, deine Sprachaufnahmen und deine Steam-Codes bleiben dort (ohne eigenen Steam-Schlüssel listet die App deine Matches über diese Website, die nichts speichert: siehe 6). Es gibt keine Konten. Was bei dieser Website ankommt: die Update-Prüfungen der App, anonyme Nutzungszähler (du kannst sie ausschalten), die Fehlermeldungen, die du selbst sendest, und deine Matches, anonymisiert (standardmäßig geteilt, du kannst es ausschalten). Diese Website setzt keine Cookies und hat keine Analyse, keine Werbung und kein Tracking.</p>
<h2>1. Diese Website</h2>
<p>Wenn du sie besuchst oder die App herunterlädst, zeichnen die Server des Hosters technische Protokolle auf (IP-Adresse, Datum und Uhrzeit, angefragte Seite oder Datei, Browser), für Sicherheit und Betrieb. Der Hoster bewahrt sie für begrenzte Zeit auf; wir nutzen sie für nichts anderes. Die Website lädt nichts von anderen Servern.</p>
<h2>2. Update-Prüfungen</h2>
<p>Die App lädt beim Start und alle paar Stunden <code>releases/latest.json</code> von dieser Website herunter, und die Update-Dateien, wenn du sie installieren willst. Diese Anfragen enthalten keine Kennung; wie jede Web-Anfrage zeigen sie dem Hoster deine IP-Adresse (siehe 1).</p>
<h2>3. Teilen deiner Matches (standardmäßig an, du kannst es ausschalten)</h2>
<p>Sofern du es nicht ausschaltest (im Hinweis beim ersten Start oder jederzeit unter Einstellungen → <i>Meine Matches mit der Datenbank teilen</i>), sendet die App, nachdem du diesen Hinweis gesehen hast, für jedes neue auf deinem PC analysierte Match die aus der Demo extrahierten Tabellen (Spielerpositionen jede halbe Sekunde, Duelle, Granaten, Käufe, Runden), nachdem sie auf deinem PC anonymisiert wurden:</p>
<ul><li>jede SteamID wird durch eine Kennung ersetzt, die mit einem zufälligen, nur für dieses Match verwendeten und nie gespeicherten Schlüssel erzeugt wird: Niemand, auch wir nicht, kann sie auf ein Konto zurückführen oder einen Spieler über zwei Matches hinweg verknüpfen;</li>
<li>alle Spielernamen werden entfernt;</li><li>die Match-Kennung von Valve wird durch eine Zufallszahl ersetzt.</li></ul>
<p>Dazu: eine zufällige Kennung deiner Installation (von der App erzeugt, nicht mit deinem Steam-Konto verknüpft), Version und Build der App, die Version des Hinweises beim ersten Start, den du gesehen hast, die Map jedes Matches und ein Fingerabdruck seiner Runden (ein zweimal geteiltes Match wird nur einmal gespeichert). Niemals deine Demos, deine Stimme, deine Einstellungen, deine Schlüssel, dein Profil oder dein Name.</p>
<ul><li><b>Zweck:</b> die Referenz-Datenbank verbessern, mit der die App Spieler vergleicht.</li>
<li><b>Rechtsgrundlage:</b> unser berechtigtes Interesse, die App mit anonymisierten Daten zu verbessern (Art. 6 Abs. 1 lit. f DSGVO): Was gesendet wird, kann weder mit dir noch mit den anderen Spielern verknüpft werden. <b>Du kannst jederzeit widersprechen</b>, indem du die Option ausschaltest: Dann wird nichts mehr gesendet.</li>
<li><b>Auf dem Server:</b> Das Empfangsskript speichert deine IP-Adresse nicht. Es behält höchstens zwei Tage lang einen Hash davon mit einem täglichen Salt, um die Sendungen pro Tag zu begrenzen. Die Dateien warten beim Hoster, bis der Computer des Herausgebers sie abholt (meist innerhalb einer Stunde), und werden dann beim Hoster gelöscht.</li>
<li><b>In der Datenbank:</b> Die Matches sind dann anonyme Daten. Sie können weder mit dir noch mit den anderen Spielern verknüpft werden und werden aufbewahrt, solange die Datenbank besteht.</li>
<li><b>Vorher:</b> Du kannst uns bitten, mit deiner Installationskennung zu löschen, was deine Installation gesendet hat (Einstellungen → Meine Matches mit der Datenbank teilen).</li></ul>
<h2>4. Fehlermeldungen und Feedback (nur, wenn du sie sendest)</h2>
<p>Der Button <i>alpha · melden</i> der App sendet, was du schreibst, deine E-Mail-Adresse nur, wenn du sie angibst (um dir zu antworten), die Version der App, deine Installationskennung und, wenn du das Häkchen gesetzt lässt, technische Details: Versionen, Windows-Version, die Seite, auf der du warst, und ihre letzten Fehler sowie das Ende des App-Logs, aus dem SteamIDs, E-Mail-Adressen, ihr bekannte Spielernamen und dein Windows-Benutzername entfernt sind. Du siehst alles vor dem Senden. Die kurze Frage „Wie lief es?“ nach einem Aufwärmen oder Match sendet nur, wenn du auf Senden drückst, das Gesicht, die Tags und die Worte, die du gewählt hast, mit dem, worum es ging (die Punktzahl des Aufwärmens oder Map und Ergebnis des Matches). Der Befehl <i>!report</i> des Trainingsservers sendet, was du tippst, mit der Übung, in der du warst, und deinem Standort auf der Map.</p>
<ul><li><b>Zweck:</b> die App korrigieren und verbessern. <b>Rechtsgrundlage:</b> deine Einwilligung, die du durch das Senden gibst.</li>
<li><b>Aufbewahrung:</b> Die Meldung wartet beim Hoster, bis der Computer des Herausgebers sie abholt (meist innerhalb einer Stunde), und wird dort dann gelöscht; der Herausgeber bewahrt sie auf, bis das Problem gelöst ist, höchstens ein Jahr.</li>
<li>Um eine Meldung löschen zu lassen oder zu erfahren, was wir aufbewahren: Schreib uns.</li></ul>
<h2>5. Anonyme Nutzungsstatistiken (du kannst sie ausschalten)</h2>
<p>Um zu wissen, welche Teile der App genutzt werden und welche nicht, und sie auf dieser Grundlage zu überarbeiten, zählt die App pro Tag: die geöffneten Seiten und die Zeit auf jeder (nur, solange die Seite angezeigt wird), die genutzten Buttons (bezeichnet durch Seite und Element, nie durch das, was darauf steht), die Anzahl der Fehler, auf die die Seite stößt, die Zeit, in der Live während eines Matches läuft, sowie die Version der App und eine Größenklasse des Bildschirms. Sonst nichts: keine Kennung (nicht einmal die der Installation), keine SteamID, kein Name, nichts, was du schreibst, keine Match-Daten.</p>
<ul><li>Ein abgeschlossener Tag wird an diese Website gesendet, zu den Summen dieses Tages aller Spieler addiert, und der Bericht selbst wird verworfen: Es bleiben nur Summen pro Tag, die mit niemandem verknüpft werden können. Deine IP-Adresse wird nicht gespeichert (zum täglichen gesalzenen Hash, der die Sendungen begrenzt, siehe 3).</li>
<li><b>Rechtsgrundlage:</b> unser berechtigtes Interesse, die Nutzung der App zu messen, unter den Bedingungen, die die CNIL für einwilligungsfreie Reichweitenmessung festlegt (nur anonyme Statistiken, nur für den Herausgeber). <b>Du kannst jederzeit widersprechen</b>: Einstellungen → Nutzungsstatistiken → Ausschalten; dann wird nichts mehr gezählt oder gesendet. Die App sagt es dir beim ersten Öffnen.</li>
<li><b>Aufbewahrung:</b> die Tagessummen höchstens 25 Monate; die Zähler auf deinem PC 30 Tage.</li></ul>
<h2>6. Deine Matches über diese Website listen (wenn du keinen eigenen Steam-Schlüssel hast)</h2>
<p>Um deine neuen Matches zu finden, fragt die App die Steam Web API von Valve nach dem nächsten Match deiner Historie. Dafür braucht es einen Steam-Web-API-Schlüssel: Wenn du deinen eigenen in der App hinzugefügt hast, fragt die App Valve direkt. Wenn nicht, sendet sie dieser Website im Inhalt einer verschlüsselten Anfrage deine SteamID, deinen Verlaufscode und den Code des letzten Matches, das sie kennt; die Website gibt sie mit ihrem eigenen Schlüssel an Valve weiter und gibt die Antwort von Valve zurück. Ebenso kann die App die öffentlichen Steam-Namen von SteamIDs und eine öffentliche Freundesliste abfragen (um deine Gruppe zu erkennen).</p>
<ul><li><b>Nichts wird gespeichert:</b> Die Codes dienen nur dieser Anfrage und werden von der Website nie in eine Datei oder ein Protokoll geschrieben. Nur ein Zähler pro Tag begrenzt die Menge (deine Adresse als Hash mit dem Salt des Tages, nach zwei Tagen gelöscht, siehe 3).</li>
<li><b>Rechtsgrundlage:</b> die Erbringung des Dienstes, den du anforderst (Art. 6 Abs. 1 lit. b DSGVO). Um das ganz zu vermeiden, füge deinen eigenen Schlüssel in den Einstellungen hinzu.</li></ul>
<h2>7. Was die App auf deinem PC macht (nicht an uns gesendet)</h2>
<ul><li><b>Verlaufscode (und dein eigener Steam-Web-API-Schlüssel, falls du einen hinzufügst):</b> in <code>out/settings.json</code> auf deinem PC gespeichert, an die Steam Web API von Valve gesendet, um deine Matches zu listen, direkt mit deinem Schlüssel oder über diese Website (siehe 6).</li>
<li><b>Die Demos deiner Matches</b> (über deinen Steam-Client von den Servern von Valve heruntergeladen) und was die App daraus extrahiert, einschließlich der anderen Spieler deiner Matches (ihre SteamIDs und Spielernamen, wie in jeder Demo): auf deinem PC verarbeitet, um dich zu coachen, und auf deinem PC gespeichert.</li>
<li><b>Stimme (optional, standardmäßig aus):</b> Die App kann während deiner Matches dein Mikrofon aufnehmen und es auf deinem PC transkribieren. Deine Mitspieler aufzunehmen (die Tonausgabe deines PCs) erfordert für jedes Match ihre Zustimmung; die App beginnt erst, nachdem du es im Spiel bestätigt hast. Aufnahmen verlassen nie deinen PC.</li>
<li><b>Dienste, die die App von deinem PC aus kontaktiert</b>, wenn du die jeweilige Funktion nutzt, nach deren eigenen Datenschutzrichtlinien: Valve (Steam Web API, Steam Community, der Spielkoordinator über deinen Steam-Client, Demo-Server), die öffentliche API von Leetify (Statistiken der Spieler, die du analysierst), GitHub (Map-Radare, ein Lineup-Buch), Hugging Face (das Spracherkennungsmodell, wenn du die Stimme nutzt).</li></ul>
<h2>8. Die Datenbank, die mit der App kommt</h2>
<p>Die App enthält Referenztabellen, berechnet aus Matchmaking-Demos von Counter-Strike 2. Jeder Spieler darin hat eine erfundene Kennung und keinen Namen. Profi-Matches (aus öffentlichen Demos, veröffentlicht von HLTV.org) behalten die öffentlichen Namen der Spieler; wenn du einer von ihnen bist und möchtest, dass ein Datenpunkt entfernt wird, kontaktiere uns.</p>
<h2>9. Deine Rechte</h2>
<p>Nach der DSGVO hast du das Recht auf Auskunft, Berichtigung und Löschung deiner personenbezogenen Daten, auf Einschränkung der Verarbeitung und Widerspruch gegen sie, auf Datenübertragbarkeit und auf Widerruf deiner Einwilligung. Kontakt: <a href="mailto:{C['contact']}">{C['contact']}</a>. Du kannst dich auch bei der CNIL (<a href="https://www.cnil.fr">www.cnil.fr</a>) oder bei der Datenschutzaufsichtsbehörde deines Landes beschweren.</p>
<h2>10. Wo die Daten liegen</h2>
<p>Der Hoster sitzt in der Schweiz, die die Europäische Kommission als Land mit angemessenem Schutzniveau anerkennt. Der Computer des Herausgebers steht in Frankreich.</p>
<h2>11. Änderungen</h2><p>Diese Seite ändert sich, wenn sich die Datennutzung der App ändert; das Datum oben ist das der letzten Aktualisierung.</p></div>"""


PRIVACY = {"de": privacy_de, "ru": privacy_ru, "pt": privacy_pt, "es": privacy_es, "zh": privacy_zh}


def terms_ru(C):
    return f"""<div class="doc"><h1>Условия использования и правовая информация</h1><p class="note">Последнее обновление: {UPDATED['ru']} · {PREVAILS['ru']} <a href="conditions.html" hreflang="fr">Версия на французском</a></p>
<h2>1. Приложение</h2><p>Wily — бесплатное приложение для Windows и Linux, которое анализирует твои матчи Counter-Strike 2 на твоём ПК и тренирует тебя во время, до и после них. Это альфа-версия, первая открытая для всех: функции могут меняться, ломаться или прекращать работу.</p>
<h2>2. Бесплатно, как есть</h2><p>Приложение предоставляется бесплатно и «как есть», без гарантий точности, бесперебойной работы или пригодности для определённой цели. Его советы основаны на статистике и могут быть ошибочными.</p>
<h2>3. Твоё использование</h2><p>Ты можешь пользоваться приложением для личных некоммерческих целей. Ты не можешь продавать его или распространять его изменённые версии. Ты отвечаешь за законное использование: для записи голоса других людей нужно их согласие (во Франции — статья 226-1 Уголовного кодекса), и приложение записывает тиммейтов только после того, как ты подтвердишь их согласие.</p>
<h2>4. Честная игра</h2><p>Приложение использует только то, что Valve предоставляет сторонним инструментам: Game State Integration, лог консоли, который пишет игра, Steam Web API и демки твоих матчей. Оно никогда не читает память игры или её сетевой трафик и никогда не действует в игре за тебя. Сервер тренировок — отдельная локальная копия игры, в которую заходишь только ты. Только Valve решает, как применяются её правила.</p>
<h2>5. Valve</h2><p>Wily не связан с Valve Corporation, не одобрен и не спонсируется ею. Counter-Strike, Counter-Strike 2, CS2 и Steam — товарные знаки Valve Corporation.</p>
<h2>6. Сторонние компоненты</h2><p>Приложение содержит стороннее ПО и данные под их собственными лицензиями: см. <a href="licenses.html">Лицензии</a>.</p>
<h2>7. Ответственность</h2><p>В пределах, допускаемых законом, издатель не несёт ответственности за косвенный ущерб, потерю данных или игровых результатов, вызванные приложением. Ничто в этих условиях не ограничивает ответственность, которую закон не позволяет ограничивать.</p>
<h2>8. Применимое право</h2><p>Эти условия регулируются правом Франции. Если ты потребитель, за тобой сохраняется защита обязательных норм твоей страны.</p>
<h2>9. Правовая информация</h2><p><b>Издатель и ответственный за публикацию:</b> {C['publisher']}, <a href="mailto:{C['contact']}">{C['contact']}</a>.<br><b>Хостинг:</b> {C['host']}.</p></div>"""


def terms_pt(C):
    return f"""<div class="doc"><h1>Termos de uso e aviso legal</h1><p class="note">Última atualização: {UPDATED['pt']} · {PREVAILS['pt']} <a href="conditions.html" hreflang="fr">Versão em francês</a></p>
<h2>1. O app</h2><p>O Wily é um app gratuito para Windows e Linux que analisa suas partidas de Counter-Strike 2 no seu PC e te treina durante, antes e depois delas. É uma alpha, a primeira versão aberta a todos: recursos podem mudar, quebrar ou parar.</p>
<h2>2. Grátis, no estado em que se encontra</h2><p>O app é fornecido gratuitamente e "no estado em que se encontra", sem garantia de que seja exato, ininterrupto ou adequado a uma finalidade específica. As dicas vêm de estatísticas e podem estar erradas.</p>
<h2>3. Seu uso</h2><p>Você pode usar o app para uso pessoal e não comercial. Você não pode vendê-lo nem distribuir versões modificadas dele. Você é responsável por usá-lo dentro da lei: gravar a voz de outras pessoas exige o consentimento delas (na França, artigo 226-1 do Código Penal), e o app só grava seus aliados depois que você confirma que eles concordaram.</p>
<h2>4. Jogo limpo</h2><p>O app usa só o que a Valve oferece a ferramentas de terceiros: Game State Integration, o log de console que o jogo escreve, a Steam Web API e as demos das suas partidas. Ele nunca lê a memória do jogo nem o tráfego de rede e nunca age no jogo por você. O servidor de treino é uma cópia local separada do jogo em que só você entra. Só a Valve decide como as regras dela se aplicam.</p>
<h2>5. Valve</h2><p>O Wily não é afiliado, endossado nem patrocinado pela Valve Corporation. Counter-Strike, Counter-Strike 2, CS2 e Steam são marcas da Valve Corporation.</p>
<h2>6. Componentes de terceiros</h2><p>O app inclui softwares e dados de terceiros sob suas próprias licenças: veja <a href="licenses.html">Licenças</a>.</p>
<h2>7. Responsabilidade</h2><p>Na medida permitida pela lei, o editor não é responsável por danos indiretos, perda de dados ou de resultados no jogo causados pelo app. Nada nestes termos limita uma responsabilidade que a lei não permite limitar.</p>
<h2>8. Lei aplicável</h2><p>Estes termos são regidos pela lei francesa. Se você é consumidor, mantém a proteção das normas obrigatórias do seu país.</p>
<h2>9. Aviso legal</h2><p><b>Editor e diretor de publicação:</b> {C['publisher']}, <a href="mailto:{C['contact']}">{C['contact']}</a>.<br><b>Hospedagem:</b> {C['host']}.</p></div>"""


def terms_es(C):
    return f"""<div class="doc"><h1>Términos de uso y aviso legal</h1><p class="note">Última actualización: {UPDATED['es']} · {PREVAILS['es']} <a href="conditions.html" hreflang="fr">Versión en francés</a></p>
<h2>1. La app</h2><p>Wily es una app gratuita para Windows y Linux que analiza tus partidas de Counter-Strike 2 en tu PC y te entrena durante, antes y después de ellas. Es una alpha, la primera versión abierta a todos: sus funciones pueden cambiar, fallar o detenerse.</p>
<h2>2. Gratis, tal cual</h2><p>La app se ofrece gratis y "tal cual", sin garantía de que sea exacta, ininterrumpida o adecuada para un fin determinado. Sus consejos vienen de estadísticas y pueden equivocarse.</p>
<h2>3. Tu uso</h2><p>Puedes usar la app para tu uso personal y no comercial. No puedes venderla ni distribuir versiones modificadas. Eres responsable de usarla conforme a la ley: grabar la voz de otras personas requiere su consentimiento (en Francia, artículo 226-1 del Código Penal), y la app solo graba a tus compañeros después de que confirmas que aceptaron.</p>
<h2>4. Juego limpio</h2><p>La app solo usa lo que Valve ofrece a herramientas de terceros: Game State Integration, el registro de consola que escribe el juego, la Steam Web API y las demos de tus partidas. Nunca lee la memoria del juego ni su tráfico de red y nunca actúa en el juego por ti. El servidor de entrenamiento es una copia local aparte del juego a la que solo entras tú. Solo Valve decide cómo se aplican sus reglas.</p>
<h2>5. Valve</h2><p>Wily no está afiliado, avalado ni patrocinado por Valve Corporation. Counter-Strike, Counter-Strike 2, CS2 y Steam son marcas de Valve Corporation.</p>
<h2>6. Componentes de terceros</h2><p>La app incluye software y datos de terceros bajo sus propias licencias: ver <a href="licenses.html">Licencias</a>.</p>
<h2>7. Responsabilidad</h2><p>En la medida en que la ley lo permita, el editor no es responsable de daños indirectos, pérdida de datos o de resultados en el juego causados por la app. Nada en estos términos limita una responsabilidad que la ley no permite limitar.</p>
<h2>8. Ley aplicable</h2><p>Estos términos se rigen por la ley francesa. Si eres consumidor, conservas la protección de las normas obligatorias de tu país.</p>
<h2>9. Aviso legal</h2><p><b>Editor y director de publicación:</b> {C['publisher']}, <a href="mailto:{C['contact']}">{C['contact']}</a>.<br><b>Alojamiento:</b> {C['host']}.</p></div>"""


def terms_zh(C):
    return f"""<div class="doc"><h1>使用条款和法律声明</h1><p class="note">最后更新：{UPDATED['zh']} · {PREVAILS['zh']}<a href="conditions.html" hreflang="fr">法文版本</a></p>
<h2>1. 应用</h2><p>Wily是一款免费的Windows和Linux应用，在你的电脑上分析你的《反恐精英2》比赛，并在赛中、赛前和赛后指导你。这是alpha版本，第一个向所有人开放的版本：功能可能会变化、出错或停止。</p>
<h2>2. 免费，按现状提供</h2><p>本应用免费并“按现状”提供，不保证其准确、不间断或适用于特定用途。它的建议来自统计数据，可能出错。</p>
<h2>3. 你的使用</h2><p>你可以将本应用用于个人、非商业用途。你不得出售本应用或分发其修改版本。你有责任合法使用：录制他人的声音需要其同意（在法国，依据《刑法典》第226-1条），且应用只有在你确认队友同意后才会录制他们。</p>
<h2>4. 公平竞技</h2><p>本应用只使用Valve向第三方工具提供的内容：游戏状态集成（Game State Integration）、游戏写入的控制台日志、Steam Web API以及你比赛的录像。它从不读取游戏内存或网络流量，也从不在游戏中替你操作。训练服务器是一份独立的本地游戏副本，只有你会加入。Valve的规则如何适用，仅由Valve决定。</p>
<h2>5. Valve</h2><p>Wily与Valve Corporation无关联，也未获其认可或赞助。Counter-Strike、Counter-Strike 2、CS2和Steam是Valve Corporation的商标。</p>
<h2>6. 第三方组件</h2><p>本应用包含第三方软件和数据，适用其各自的许可证：见<a href="licenses.html">许可证</a>。</p>
<h2>7. 责任</h2><p>在法律允许的范围内，发布者不对本应用造成的间接损失、数据丢失或游戏成绩损失承担责任。本条款中的任何内容均不限制法律不允许限制的责任。</p>
<h2>8. 适用法律</h2><p>本条款受法国法律管辖。如果你是消费者，你仍受你所在国家强制性规定的保护。</p>
<h2>9. 法律声明</h2><p><b>发布者及出版负责人：</b>{C['publisher']}，<a href="mailto:{C['contact']}">{C['contact']}</a>。<br><b>托管服务商：</b>{C['host']}。</p></div>"""


def terms_de(C):
    return f"""<div class="doc"><h1>Nutzungsbedingungen und Impressum</h1><p class="note">Zuletzt aktualisiert: {UPDATED['de']} · {PREVAILS['de']} <a href="conditions.html" hreflang="fr">Französische Fassung</a></p>
<h2>1. Die App</h2><p>Wily ist eine kostenlose App für Windows und Linux, die deine Matches in Counter-Strike 2 auf deinem PC analysiert und dich während, vor und nach ihnen coacht. Es ist eine Alpha, die erste Version, die für alle offen ist: Funktionen können sich ändern, kaputtgehen oder wegfallen.</p>
<h2>2. Kostenlos, wie sie ist</h2><p>Die App wird kostenlos und „wie sie ist“ bereitgestellt, ohne Gewähr, dass sie genau, unterbrechungsfrei oder für einen bestimmten Zweck geeignet ist. Ihre Tipps beruhen auf Statistiken und können falsch sein.</p>
<h2>3. Deine Nutzung</h2><p>Du darfst die App für deine eigene, nicht kommerzielle Nutzung verwenden. Du darfst sie weder verkaufen noch veränderte Versionen davon verbreiten. Du bist für eine rechtmäßige Nutzung verantwortlich: Die Stimmen anderer aufzunehmen erfordert ihre Einwilligung (in Frankreich Artikel 226-1 des Code pénal, in Deutschland § 201 StGB), und die App nimmt deine Mitspieler erst auf, nachdem du bestätigt hast, dass sie zugestimmt haben.</p>
<h2>4. Fair Play</h2><p>Die App nutzt nur, was Valve Drittanbieter-Tools bereitstellt: Game State Integration, das Konsolen-Log, das das Spiel schreibt, die Steam Web API und die Demos deiner Matches. Sie liest nie den Speicher oder den Netzwerkverkehr des Spiels und handelt im Spiel nie für dich. Der Trainingsserver ist eine separate lokale Kopie des Spiels, der nur du beitrittst. Allein Valve entscheidet, wie seine Regeln angewendet werden.</p>
<h2>5. Valve</h2><p>Wily ist nicht mit der Valve Corporation verbunden und wird von ihr weder unterstützt noch gesponsert. Counter-Strike, Counter-Strike 2, CS2 und Steam sind Marken der Valve Corporation.</p>
<h2>6. Komponenten Dritter</h2><p>Die App enthält Software und Daten Dritter unter deren eigenen Lizenzen: siehe <a href="licenses.html">Lizenzen</a>.</p>
<h2>7. Haftung</h2><p>Soweit gesetzlich zulässig, haftet der Herausgeber nicht für mittelbare Schäden, Datenverlust oder Verlust von Spielergebnissen, die durch die App verursacht werden. Nichts in diesen Bedingungen beschränkt eine Haftung, die nach dem Gesetz nicht beschränkt werden darf.</p>
<h2>8. Anwendbares Recht</h2><p>Diese Bedingungen unterliegen französischem Recht. Wenn du Verbraucher bist, behältst du den Schutz der zwingenden Vorschriften deines Landes.</p>
<h2>9. Impressum</h2><p><b>Herausgeber und verantwortlich für den Inhalt:</b> {C['publisher']}, <a href="mailto:{C['contact']}">{C['contact']}</a>.<br><b>Hosting:</b> {C['host']}.</p></div>"""


TERMS = {"de": terms_de, "ru": terms_ru, "pt": terms_pt, "es": terms_es, "zh": terms_zh}
