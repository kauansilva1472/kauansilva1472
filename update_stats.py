"""Atualiza a seção "GitHub Stats" do dark_mode.svg com números reais.
Roda sozinho todo dia pelo GitHub Actions (veja .github/workflows/update-stats.yml)."""
import json, os, re, sys, time, urllib.request
from datetime import datetime, timezone

USER = os.environ.get("USER_NAME", "kauansilva1472")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
SVG = "dark_mode.svg"
X = 390          # coluna da direita (igual ao resto do cartão)
N = 58           # largura em caracteres, depois do ". "
LEFT_W = 34      # largura da metade esquerda das linhas duplas
START, END = "<!--STATS_START-->", "<!--STATS_END-->"


def fmt(n):
    return f"{int(n):,}"


def dots(n):
    return " " + "." * max(n, 3) + " "


def build_block(s, y0=450):
    """Gera as 3 linhas de estatísticas (SVG) a partir do dicionário s."""
    lines = []
    # linha 1: Repos {Contributed} | Stars
    lv = f'{fmt(s["repos"])} {{Contributed: {fmt(s["contrib"])}}}'
    rv = fmt(s["stars"])
    ld = LEFT_W - len("Repos:") - len(lv) - 2
    rd = (N - LEFT_W - 3) - len("Stars:") - len(rv) - 2
    lines.append(
        f'<tspan x="{X}" y="{y0}" class="cc">. </tspan><tspan class="key">Repos</tspan>:'
        f'<tspan class="cc">{dots(ld)}</tspan><tspan class="value">{fmt(s["repos"])}</tspan>'
        f' {{<tspan class="key">Contributed</tspan>: <tspan class="value">{fmt(s["contrib"])}</tspan>}}'
        f' | <tspan class="key">Stars</tspan>:<tspan class="cc">{dots(rd)}</tspan>'
        f'<tspan class="value">{rv}</tspan>')
    # linha 2: Commits | Followers
    lv, rv = fmt(s["commits"]), fmt(s["followers"])
    ld = LEFT_W - len("Commits:") - len(lv) - 2
    rd = (N - LEFT_W - 3) - len("Followers:") - len(rv) - 2
    lines.append(
        f'<tspan x="{X}" y="{y0+20}" class="cc">. </tspan><tspan class="key">Commits</tspan>:'
        f'<tspan class="cc">{dots(ld)}</tspan><tspan class="value">{lv}</tspan>'
        f' | <tspan class="key">Followers</tspan>:<tspan class="cc">{dots(rd)}</tspan>'
        f'<tspan class="value">{rv}</tspan>')
    # linha 3: linhas de código
    total, add, dele = fmt(s["loc"]), fmt(s["add"]), fmt(s["del"])
    tail = f"{total} ( {add}++, {dele}-- )"
    d = N - len("Lines of Code:") - len(tail) - 2
    lines.append(
        f'<tspan x="{X}" y="{y0+40}" class="cc">. </tspan><tspan class="key">Lines of Code</tspan>:'
        f'<tspan class="cc">{dots(d)}</tspan><tspan class="value">{total}</tspan>'
        f' ( <tspan class="addColor">{add}</tspan><tspan class="addColor">++</tspan>, '
        f'<tspan class="delColor">{dele}</tspan><tspan class="delColor">--</tspan> )')
    return "\n".join(lines)


def api(url, data=None):
    req = urllib.request.Request(url, data=data)
    req.add_header("Authorization", f"bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, json.loads(r.read() or b"null")


def graphql(query, **variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    _, d = api("https://api.github.com/graphql", body)
    if "errors" in d:
        raise RuntimeError(d["errors"])
    return d["data"]


def fetch_stats():
    q = """query($u:String!){user(login:$u){createdAt followers{totalCount}
      repositoriesContributedTo(first:1,contributionTypes:[COMMIT,PULL_REQUEST,ISSUE,REPOSITORY]){totalCount}
      repositories(first:100,ownerAffiliations:OWNER,privacy:PUBLIC){totalCount
        nodes{name isFork stargazerCount}}}}"""
    u = graphql(q, u=USER)["user"]
    repos = u["repositories"]["nodes"]
    stats = {
        "repos": u["repositories"]["totalCount"],
        "contrib": u["repositoriesContributedTo"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in repos),
        "followers": u["followers"]["totalCount"],
    }
    # commits: soma ano a ano desde que a conta foi criada
    created = datetime.fromisoformat(u["createdAt"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    cq = """query($u:String!,$f:DateTime!,$t:DateTime!){user(login:$u){
      contributionsCollection(from:$f,to:$t){totalCommitContributions
      restrictedContributionsCount}}}"""
    total = 0
    for year in range(created.year, now.year + 1):
        f = max(created, datetime(year, 1, 1, tzinfo=timezone.utc))
        t = min(now, datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc))
        c = graphql(cq, u=USER, f=f.isoformat(), t=t.isoformat())["user"]["contributionsCollection"]
        total += c["totalCommitContributions"] + c["restrictedContributionsCount"]
    stats["commits"] = total
    # linhas adicionadas/removidas por você nos seus repositórios (não conta forks)
    add = dele = 0
    for r in repos:
        if r["isFork"]:
            continue
        url = f"https://api.github.com/repos/{USER}/{r['name']}/stats/contributors"
        for _ in range(6):                      # o GitHub calcula na hora: 202 = "tente de novo"
            status, data = api(url)
            if status == 200:
                break
            time.sleep(5)
        for c in data or []:
            if c["author"] and c["author"]["login"].lower() == USER.lower():
                for w in c["weeks"]:
                    add += w["a"]; dele += w["d"]
    stats.update(add=add, **{"del": dele, "loc": add - dele})
    return stats


def write_svg(stats, path=SVG):
    svg = open(path, encoding="utf-8").read()
    block = f"{START}\n{build_block(stats)}\n{END}"
    new = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda m: block, svg, flags=re.S)
    open(path, "w", encoding="utf-8").write(new)


if __name__ == "__main__":
    write_svg(fetch_stats())
    print("Estatísticas atualizadas!")