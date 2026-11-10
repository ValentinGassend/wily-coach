"""The site's pages beyond the home and the legal ones (03/11, search: the research of that day found Wily unindexed and the
queries it can win little contested: "leetify alternative", "refrag alternative", "cs2 clutch practice", "cs2 bots
training", "analyse demo cs2"): a comparison with the tools players look at, dated, each line with its source; a guide to
practise the duels you lost, with Wily and by hand. English and French; the other languages link to their home.

    PAGES[kind][lang] = (file, title, description, body)"""

DATE = {"en": "3 November 2026", "fr": "3 novembre 2026"}

SRC = {
    "leetify": "https://leetify.com/",
    "refrag": "https://refrag.gg/",
    "refrag_restrat": "https://refrag.gg/blog/hltv-demos-now-available-on-refrag",
    "refrag_coach": "https://refrag.gg/blog/announcing-refrag-coach-the-easiest-way-to-track-analyze-and-practice-for-cs2",
    "scope": "https://scope.gg/",
    "pureskill": "https://pureskill.gg/",
    "csdm": "https://github.com/akiver/cs-demo-manager",
}


def _src(k, label):
    return f'<a href="{SRC[k]}" rel="nofollow noopener">{label}</a>'


def compare_en(C):
    return f"""<div class="doc wide">
<h1>Wily compared with Leetify, Refrag, Scope.gg, PureSkill and CS Demo Manager</h1>
<p class="lede">Wily is a free, open-source (Apache 2.0) CS2 coach that runs on your PC. Bots replay the duels you lost in
your own matches on a local training server, it gives live advice on a second screen during matches, and it reviews your
demos round by round. This page compares it with the tools CS2 players usually look at.</p>
<p class="note">As listed on each tool's own pages on {DATE['en']}. Prices and features change: each line links to its
source. Something wrong or outdated? Write to <a href="mailto:{C['contact']}">{C['contact']}</a> and it gets fixed.</p>
<div class="tablewrap"><table class="cmp">
<thead><tr><th>Tool</th><th>What it does</th><th>Price</th><th>Runs</th><th>Bots replay your own deaths</th><th>Open source</th></tr></thead>
<tbody>
<tr class="me"><th>Wily</th><td>Review of your matchmaking demos, a local training server (your deaths and clutches replayed, grenades, defense, prefire), live advice through Game State Integration</td><td>Free</td><td>Your PC (Windows, Linux)</td><td>Yes, from your own matches</td><td>Yes, <a href="{C['github']}">Apache 2.0</a></td></tr>
<tr><th>{_src('leetify', 'Leetify')}</th><td>Stats, highlights and 2D replays of your matches</td><td>Free, paid Pro</td><td>Web</td><td>No</td><td>No</td></tr>
<tr><th>{_src('refrag', 'Refrag')}</th><td>Hosted practice servers (prefire, utility, crossfire, retakes); {_src('refrag_coach', 'Refrag Coach')} recommends a mode from your history; {_src('refrag_restrat', 'Restrat')} replays rounds from HLTV demos</td><td>Paid, from about $5.83 a month (yearly)</td><td>Hosted servers</td><td>No (Restrat uses HLTV demos)</td><td>No</td></tr>
<tr><th>{_src('scope', 'Scope.gg')}</th><td>Mistakes with fixes, 2D viewer, clips, progress</td><td>Free core, paid premium</td><td>Web</td><td>No</td><td>No</td></tr>
<tr><th>{_src('pureskill', 'PureSkill.gg')}</th><td>"Automated coach": assessments of your Premier and FACEIT matches, the moment of each mistake in 2D</td><td>Free start</td><td>Web</td><td>No</td><td>No</td></tr>
<tr><th>{_src('csdm', 'CS Demo Manager')}</th><td>Desktop app to download, organize and analyze your demos (stats, heatmaps, 2D)</td><td>Free</td><td>Your PC</td><td>No</td><td>Yes (MIT)</td></tr>
</tbody></table></div>
<h2>Which one for what</h2>
<ul>
<li><b>Stats in the browser, nothing to install:</b> Leetify, Scope.gg or PureSkill.gg.</li>
<li><b>Hosted servers with many practice modes, fine paying a subscription:</b> Refrag.</li>
<li><b>A library of your demos with heatmaps and a 2D viewer:</b> CS Demo Manager.</li>
<li><b>Replaying the exact duels you lost, everything on your PC, free and open:</b> Wily. See how in
<a href="practice-lost-duels.html">practising the duels you lost</a>.</li>
</ul>
<h2>What to know before trying Wily</h2>
<ul>
<li>It is an alpha (0.0.1): the first version open to all players, expect rough edges.</li>
<li>It reads only what Valve provides: Game State Integration, the console log, the Steam Web API, your demos. It never
reads the game's memory or network traffic.</li>
<li>Your demos, profile and voice stay on your PC; anonymized match tables are shared by default to grow the base, one
click turns it off (<a href="privacy.html">privacy policy</a>).</li>
</ul>
<p><a class="btn" href="./#download">Download Wily</a></p>
</div>"""


def compare_fr(C):
    return f"""<div class="doc wide">
<h1>Wily comparé à Leetify, Refrag, Scope.gg, PureSkill et CS Demo Manager</h1>
<p class="lede">Wily est un coach CS2 gratuit et open source (Apache 2.0) qui tourne sur ton PC. Des bots rejouent les
duels que tu as perdus dans tes propres matchs, sur un serveur d'entraînement local ; il te conseille en direct sur un
deuxième écran pendant tes matchs ; il analyse tes démos round par round. Cette page le compare aux outils que les joueurs
de CS2 regardent d'habitude.</p>
<p class="note">D'après les pages de chaque outil au {DATE['fr']}. Les prix et les fonctions changent : chaque ligne renvoie
à sa source. Une erreur, une info périmée ? Écris à <a href="mailto:{C['contact']}">{C['contact']}</a>, je corrige.</p>
<div class="tablewrap"><table class="cmp">
<thead><tr><th>Outil</th><th>Ce qu'il fait</th><th>Prix</th><th>Où il tourne</th><th>Des bots rejouent tes propres morts</th><th>Open source</th></tr></thead>
<tbody>
<tr class="me"><th>Wily</th><td>Analyse de tes démos de matchmaking, un serveur d'entraînement local (tes morts et tes clutchs rejoués, grenades, défense, prefire), des conseils en direct par le Game State Integration</td><td>Gratuit</td><td>Ton PC (Windows, Linux)</td><td>Oui, depuis tes propres matchs</td><td>Oui, <a href="{C['github']}">Apache 2.0</a></td></tr>
<tr><th>{_src('leetify', 'Leetify')}</th><td>Statistiques, temps forts et replays 2D de tes matchs</td><td>Gratuit, Pro payant</td><td>Web</td><td>Non</td><td>Non</td></tr>
<tr><th>{_src('refrag', 'Refrag')}</th><td>Serveurs d'entraînement hébergés (prefire, grenades, crossfire, retakes) ; {_src('refrag_coach', 'Refrag Coach')} recommande un mode d'après ton historique ; {_src('refrag_restrat', 'Restrat')} rejoue des rounds de démos HLTV</td><td>Payant, à partir d'environ 5,83 $ par mois (à l'année)</td><td>Serveurs hébergés</td><td>Non (Restrat part de démos HLTV)</td><td>Non</td></tr>
<tr><th>{_src('scope', 'Scope.gg')}</th><td>Erreurs et corrections, visionneuse 2D, clips, progression</td><td>Base gratuite, premium payant</td><td>Web</td><td>Non</td><td>Non</td></tr>
<tr><th>{_src('pureskill', 'PureSkill.gg')}</th><td>« Coach automatique » : évaluations de tes matchs Premier et FACEIT, le moment de chaque erreur en 2D</td><td>Départ gratuit</td><td>Web</td><td>Non</td><td>Non</td></tr>
<tr><th>{_src('csdm', 'CS Demo Manager')}</th><td>Application de bureau pour télécharger, ranger et analyser tes démos (stats, cartes de chaleur, 2D)</td><td>Gratuit</td><td>Ton PC</td><td>Non</td><td>Oui (MIT)</td></tr>
</tbody></table></div>
<h2>Lequel pour quoi</h2>
<ul>
<li><b>Des stats dans le navigateur, rien à installer :</b> Leetify, Scope.gg ou PureSkill.gg.</li>
<li><b>Des serveurs hébergés avec beaucoup de modes, un abonnement ne te gêne pas :</b> Refrag.</li>
<li><b>Une bibliothèque de tes démos avec cartes de chaleur et visionneuse 2D :</b> CS Demo Manager.</li>
<li><b>Rejouer exactement les duels que tu as perdus, tout sur ton PC, gratuit et ouvert :</b> Wily. Voir comment dans
<a href="rejouer-duels-perdus.html">rejouer les duels perdus</a>.</li>
</ul>
<h2>À savoir avant d'essayer Wily</h2>
<ul>
<li>C'est une alpha (0.0.1) : la première version ouverte à tous, des défauts restent à corriger.</li>
<li>Il ne lit que ce que Valve fournit : le Game State Integration, le journal de console, l'API Steam, tes démos. Jamais
la mémoire du jeu ni son trafic réseau.</li>
<li>Tes démos, ton profil et ta voix restent sur ton PC ; des tables de matchs anonymisées sont partagées par défaut pour
enrichir la base, un clic le coupe (<a href="confidentialite.html">politique de confidentialité</a>).</li>
</ul>
<p><a class="btn" href="fr.html#download">Télécharger Wily</a></p>
</div>"""


def guide_en(C):
    return f"""<div class="doc">
<h1>How to practise the duels you lost in CS2, with bots</h1>
<p class="lede">Find the round in your demo, note where you stood and where the enemy came from, then take that exact duel
again against a bot until you win it, changing one thing at a time. Wily does the first three steps for you; you can also
do them by hand with a few console commands.</p>
<p class="note">Updated {DATE['en']}.</p>
<h2>Why the duels you lost, and not random ones</h2>
<p>An aim map trains your aim on targets that never stand where your opponents do. The duels you lost show the spots,
angles and timings where you actually lose rounds: the same corner taken too wide, the same peek against a held angle.
Replaying those, at the same place and from the same direction, trains the decision as well as the shot.</p>
<h2>With Wily (a few clicks)</h2>
<ol class="steps">
<li>Install Wily and connect CS2: it finds your Steam account and analyzes your matchmaking matches on your PC, a few
minutes each.</li>
<li>Open <b>Prepare</b>, pick a map and start a warm-up: the training server installs itself the first time, on your
CS2's own files.</li>
<li>Bots come back exactly where they killed you in your real matches, from the side they came. Take the duel again
until you win it; each drill tells you how it went and what changed.</li>
</ol>
<p><a class="btn" href="./#download">Download Wily (free)</a></p>
<h2>By hand (no tool)</h2>
<ol class="steps">
<li><b>Find the round.</b> Open your demo with <code>playdemo name</code> and the demo controls with <code>demoui</code>;
go to your death and note the round and the time.</li>
<li><b>Note the spots.</b> Pause on the duel: stand where you were and type <code>getpos</code> (it prints your position
and view); do the same where your opponent stood.</li>
<li><b>Set up a private match</b> on that map with cheats on: <code>sv_cheats 1</code>, <code>bot_kick</code>, then
<code>bot_add_t</code> (or <code>bot_add_ct</code>).</li>
<li><b>Place the bot</b> where your opponent stood: go there with <code>setpos x y z</code> (the numbers from getpos),
look the way they looked and type <code>bot_place</code>; <code>bot_stop 1</code> keeps it still.</li>
<li><b>Take the duel</b> from your own spot: <code>setpos</code> back to where you were and peek. Repeat it ten times.</li>
</ol>
<p>By hand the bot stands still and never shoots back the way your opponent did; Wily's bots walk the way the real
player came, react and fight back.</p>
<h2>What to change from one try to the next</h2>
<ul>
<li>Where your crosshair waits before the peek: at head height, on the edge the enemy appears from.</li>
<li>How you peek: a wide swing, a jiggle for information, or holding the angle instead.</li>
<li>Your stop before the shot (counter-strafe), and the first bullet's timing.</li>
<li>Whether the duel was worth taking at all: a teammate's trade, a grenade first, or another way round.</li>
</ul>
<p>See also: <a href="compare.html">Wily compared with Leetify, Refrag, Scope.gg and CS Demo Manager</a>.</p>
</div>"""


def guide_fr(C):
    return f"""<div class="doc">
<h1>Rejouer les duels perdus dans CS2, contre des bots</h1>
<p class="lede">Retrouve le round dans ta démo, note où tu étais et d'où l'adversaire est arrivé, puis rejoue ce duel
précis contre un bot jusqu'à le gagner, en changeant une seule chose à la fois. Wily fait les trois premières étapes pour
toi ; tu peux aussi les faire à la main avec quelques commandes de console.</p>
<p class="note">Mis à jour le {DATE['fr']}.</p>
<h2>Pourquoi les duels perdus, et pas des duels au hasard</h2>
<p>Une map d'aim entraîne ta visée sur des cibles qui ne se tiennent jamais là où se tiennent tes adversaires. Les duels
perdus montrent les spots, les angles et les timings où tu perds vraiment des rounds : le même coin pris trop large, le
même peek face à un angle tenu. Les rejouer au même endroit et dans le même sens entraîne la décision autant que le tir.</p>
<h2>Avec Wily (quelques clics)</h2>
<ol class="steps">
<li>Installe Wily et connecte CS2 : il trouve ton compte Steam et analyse tes matchs de matchmaking sur ton PC, quelques
minutes chacun.</li>
<li>Ouvre <b>Préparer</b>, choisis une map et lance un échauffement : le serveur d'entraînement s'installe la première
fois, sur les fichiers de ton CS2.</li>
<li>Les bots reviennent exactement là où ils t'ont tué dans tes vrais matchs, du côté d'où ils sont venus. Rejoue le duel
jusqu'à le gagner ; chaque exercice te dit comment ça s'est passé et ce qui a changé.</li>
</ol>
<p><a class="btn" href="fr.html#download">Télécharger Wily (gratuit)</a></p>
<h2>À la main (sans outil)</h2>
<ol class="steps">
<li><b>Retrouve le round.</b> Ouvre ta démo avec <code>playdemo nom</code> et ses contrôles avec <code>demoui</code> ; va
à ta mort et note le round et le moment.</li>
<li><b>Note les spots.</b> Mets en pause sur le duel : place-toi là où tu étais et tape <code>getpos</code> (il affiche ta
position et ta vue) ; fais pareil là où se tenait ton adversaire.</li>
<li><b>Lance un match privé</b> sur cette map avec les cheats : <code>sv_cheats 1</code>, <code>bot_kick</code>, puis
<code>bot_add_t</code> (ou <code>bot_add_ct</code>).</li>
<li><b>Place le bot</b> là où était ton adversaire : vas-y avec <code>setpos x y z</code> (les nombres de getpos), regarde
dans sa direction et tape <code>bot_place</code> ; <code>bot_stop 1</code> le garde immobile.</li>
<li><b>Rejoue le duel</b> depuis ton spot : <code>setpos</code> pour revenir où tu étais, et peek. Recommence dix fois.</li>
</ol>
<p>À la main, le bot reste immobile et ne riposte jamais comme ton adversaire ; les bots de Wily prennent le chemin du
vrai joueur, réagissent et se battent.</p>
<h2>Ce qu'il faut changer d'un essai à l'autre</h2>
<ul>
<li>Où ton viseur attend avant le peek : à hauteur de tête, sur le bord d'où l'ennemi apparaît.</li>
<li>Comment tu peeks : un swing large, un jiggle pour l'info, ou tenir l'angle à la place.</li>
<li>Ton arrêt avant le tir (le contre-strafe) et le moment de la première balle.</li>
<li>Si le duel valait la peine : le trade d'un coéquipier, une grenade d'abord, ou un autre chemin.</li>
</ul>
<p>Voir aussi : <a href="comparatif.html">Wily comparé à Leetify, Refrag, Scope.gg et CS Demo Manager</a>.</p>
</div>"""


PAGES = {
    "compare": {
        "en": ("compare.html", "Leetify & Refrag alternative · Wily CS2 Coach compared",
               "Wily CS2 Coach compared with Leetify, Refrag, Scope.gg, PureSkill.gg and CS Demo Manager: what each does, price, "
               "where it runs, and which replays your own deaths with bots.", compare_en),
        "fr": ("comparatif.html", "Alternative à Leetify et Refrag · Wily CS2 Coach comparé",
               "Wily CS2 Coach comparé à Leetify, Refrag, Scope.gg, PureSkill.gg et CS Demo Manager : ce que fait chacun, le prix, "
               "où il tourne, et lequel rejoue tes propres morts avec des bots.", compare_fr),
    },
    "guide": {
        "en": ("practice-lost-duels.html", "How to practise the duels you lost in CS2 with bots · Wily",
               "Practise the exact duels you lost in your CS2 matches: find the round, note the spots, replay it against a bot. "
               "With Wily in a few clicks, or by hand with console commands.", guide_en),
        "fr": ("rejouer-duels-perdus.html", "Rejouer les duels perdus dans CS2 contre des bots · Wily",
               "Rejoue les duels précis perdus dans tes matchs CS2 : retrouve le round, note les spots, rejoue-le contre un bot. "
               "Avec Wily en quelques clics, ou à la main avec des commandes de console.", guide_fr),
    },
}
