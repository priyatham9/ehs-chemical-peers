"""The story page is generated, never hand-typed.

Checks: the build is idempotent, no template token survives, unknown tokens
fail loudly, and the numbers in the key sentences match outputs/summary.json.
Run: python3 -m unittest tests.test_story
"""
import html
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "story.html"
SUMMARY = json.loads((ROOT / "outputs" / "summary.json").read_text(encoding="utf-8"))
sys.path.insert(0, str(ROOT / "scripts"))
import build_story  # noqa: E402


# The full build inlines the shared story engine and header from the research
# workspace (tools/ at the Research root, repos/grounded/tools). A clone of this
# repo alone (CI) has neither, so it checks the committed page instead.
CAN_BUILD = build_story.INLINER.exists() and (ROOT.parent / "grounded" / "tools" / "banner.py").exists()


def build():
    if not CAN_BUILD:
        return OUT.read_bytes()
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_story.py")], check=True,
                   capture_output=True, cwd=ROOT)
    return OUT.read_bytes()


def visible_sentences(page):
    body = page.split("<main", 1)[1].split("</main>", 1)[0]
    body = re.sub(r"<(script|style)\b.*?</\1>", " ", body, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", " ", body))
    text = re.sub(r"\s+", " ", text)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def n0(v):
    return "{:,}".format(int(round(v)))


def n1(v):
    return "{:,.1f}".format(v)


def n2(v):
    return "{:,.2f}".format(v)


class StoryBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.first = build()
        cls.page = OUT.read_text(encoding="utf-8")
        cls.sentences = visible_sentences(cls.page)

    @unittest.skipUnless(CAN_BUILD, "shared engine and header tools not present")
    def test_idempotent(self):
        self.assertEqual(self.first, build(), "building twice changed docs/story.html")

    def test_no_tokens_left(self):
        self.assertNotIn("{{", self.page)
        self.assertNotIn("<!--STORY_DATA-->", self.page)

    def test_engine_and_header_inlined(self):
        self.assertIn('id="story-data"', self.page)
        self.assertIn('id="gsap-gsap"', self.page)
        between = self.page.split("/*STORY_JS_START*/", 1)[1].split("/*STORY_JS_END*/", 1)[0]
        self.assertGreater(len(between), 10000, "story engine was not inlined")

    def test_unknown_token_is_an_error(self):
        with self.assertRaises(SystemExit):
            build_story.render("x {{size_noise[9].nope}} y", build_story.context())
        with self.assertRaises(SystemExit):
            build_story.render("{{coverage.no_such_key}}", build_story.context())

    def test_no_dashes_or_banned_words(self):
        prose = " ".join(self.sentences)
        self.assertNotIn("—", prose)
        self.assertNotIn("–", prose)
        for w in ("delve", "crucial", "pivotal", "robust", "landscape", "Poisson", "Spearman", "funnel limits"):
            body = prose.split("How we did this", 1)[0]
            self.assertNotIn(w.lower(), body.lower(), "%r in the story body" % w)

    def sentence(self, phrase):
        hits = [s for s in self.sentences if phrase in s]
        self.assertTrue(hits, "no sentence contains %r" % phrase)
        return hits[0]

    def assertSays(self, phrase, *values):
        s = self.sentence(phrase)
        nums = re.findall(r"\d[\d,]*(?:\.\d+)?", s)
        for v in values:
            self.assertIn(v, nums, "%r should state %s; found %s" % (s, v, nums))

    def test_key_sentences_match_summary(self):
        s = SUMMARY
        sn, st, rp = s["size_noise"], s["stability"], s["release_predictors"]
        rel = s["trir_vs_outcomes"]["release_next_year"]
        self.assertSays("We followed", n0(s["coverage"]["plants"]))
        self.assertSays("works about", n0(sn[1]["median_hours"]))
        self.assertSays("One recordable injury moves its rate by", n2(sn[1]["one_case_swing"]))
        self.assertSays("the same injury moves the rate by", n2(sn[4]["one_case_swing"]))
        self.assertSays("ended with zero recordable injuries", n0(sn[1]["zero_share_pct"]))
        self.assertSays("For the smallest plants the score is", n2(st[0]["rho"]))
        self.assertSays("For the largest it is", n2(st[-1]["rho"]))
        self.assertSays("of the lower-rate half had a release", n1(rel[0]["below_median"]["pct"]), n1(rel[0]["above_median"]["pct"]))
        self.assertSays("Plants with one had another the next year", n1(rp["history"]["release_in_past_5y"]["pct"]))
        self.assertSays("Plants without:", n1(rp["history"]["no_release_in_past_5y"]["pct"]))
        self.assertSays("times the chance", "{:g}".format(rp["history_ratio"]))
        self.assertSays("It climbs from", n1(rp["inventory"][0]["pct"]), n1(rp["inventory"][-1]["pct"]))
        ev = s["injury_anatomy_all"]
        caught = next(r["n"] for r in ev["energy"] if r["label"] == "Caught in machinery")
        self.assertSays("Machinery leads by a wide margin", n0(100.0 * caught / ev["events"]))
        fa = s["release_anatomy_formaldehyde"]
        self.assertSays("releases that involved formaldehyde itself", n0(fa["releases"]), n0(fa["worker_injuries"]))

    def test_green_dashboard_stat(self):
        pct = n0(SUMMARY["green_dashboard"]["prior_year_zero_pct"])
        self.assertRegex(self.page, r'class="big-stat"[^>]*>%s%%<' % re.escape(pct))
        self.assertSays("where we could see the prior year's log",
                        n0(SUMMARY["green_dashboard"]["serious_injuries_with_prior_year"]))

    def test_chart_data_is_the_summary(self):
        blob = self.page.split('<script type="application/json" id="story-data">', 1)[1].split("</script>", 1)[0]
        data = json.loads(blob)
        for k in SUMMARY:
            self.assertEqual(data[k], SUMMARY[k], "chart data for %s differs from summary.json" % k)


if __name__ == "__main__":
    unittest.main()
