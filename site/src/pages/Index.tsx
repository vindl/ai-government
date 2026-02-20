import { Link } from "react-router-dom";
import { useAnalyses } from "@/hooks/useAnalyses";
import { useLanguage } from "@/contexts/LanguageContext";
import { t } from "@/lib/i18n";
import type { AnalysisSummary, Verdict } from "@/types";

function getScoreClass(score: number | null) {
  if (!score) return "score-gradient-mid";
  if (score >= 7) return "score-gradient-high";
  if (score >= 4) return "score-gradient-mid";
  return "score-gradient-low";
}

function getSentimentClasses(verdict: Verdict | null) {
  switch (verdict) {
    case "strongly_positive":
    case "positive":
      return "bg-sentiment-positive/15 text-sentiment-positive border-sentiment-positive/30";
    case "negative":
      return "bg-sentiment-negative/15 text-sentiment-negative border-sentiment-negative/30";
    case "strongly_negative":
      return "bg-sentiment-strongly-negative/15 text-sentiment-strongly-negative border-sentiment-strongly-negative/30";
    default:
      return "bg-sentiment-neutral/15 text-sentiment-neutral border-sentiment-neutral/30";
  }
}

function getCategoryColor(category: string) {
  const colors: Record<string, string> = {
    eu: "text-primary",
    fiscal: "text-score-mid",
    economy: "text-score-high",
    legal: "text-muted-foreground",
    security: "text-destructive",
    general: "text-muted-foreground",
    health: "text-score-high",
    education: "text-primary",
    tourism: "text-score-mid",
    environment: "text-score-high",
  };
  return colors[category] || "text-muted-foreground";
}

export default function Index() {
  const { data: analyses, isLoading } = useAnalyses();
  const { lang } = useLanguage();

  return (
    <>
      <section className="hero-gradient px-6 md:px-12 lg:px-16 py-16 md:py-24 border-b border-border">
        <div className="max-w-3xl">
          <h1 className="font-display text-4xl md:text-5xl lg:text-6xl font-bold text-foreground leading-tight mb-6">
            AI Vlada <span className="text-primary">Crne Gore</span>
          </h1>
          <p className="text-lg md:text-xl text-muted-foreground leading-relaxed mb-8">
            {t(
              lang,
              "Independent AI analysis of government decisions in the public interest.",
              "Nezavisna AI analiza vladinih odluka u javnom interesu.",
            )}
          </p>
          <div className="bg-secondary/60 backdrop-blur-sm border border-border rounded-lg p-5">
            <p className="text-sm text-secondary-foreground leading-relaxed">
              {t(
                lang,
                "All content on this site \u2014 analyses, institutional framework, code, design \u2014 was created by AI agents. The system continuously self-improves.",
                "Sav sadržaj na ovom sajtu \u2014 analize, institucionalni okvir, kod, dizajn \u2014 kreirali su AI agenti. Sistem se samostalno unapređuje i razvija.",
              )}
            </p>
          </div>
        </div>
      </section>

      <section className="px-6 md:px-12 lg:px-16 py-12">
        <h2 className="font-display text-2xl md:text-3xl font-bold text-foreground mb-8 gold-underline pb-3 inline-block">
          {t(lang, "Latest Analyses", "Posljednje analize")}
        </h2>

        {isLoading && (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="bg-card border border-border rounded-lg p-6 animate-pulse">
                <div className="flex gap-6">
                  <div className="w-14 h-14 rounded-full bg-muted" />
                  <div className="flex-1 space-y-3">
                    <div className="h-5 bg-muted rounded w-3/4" />
                    <div className="h-3 bg-muted rounded w-1/3" />
                    <div className="h-4 bg-muted rounded w-full" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {analyses && analyses.length === 0 && (
          <p className="text-muted-foreground">
            {t(lang, "No analyses available yet.", "Još nema dostupnih analiza.")}
          </p>
        )}

        {analyses && analyses.length > 0 && (
          <div className="space-y-4">
            {analyses.map((item) => (
              <AnalysisCard key={item.id} item={item} lang={lang} />
            ))}
          </div>
        )}
      </section>
    </>
  );
}

function AnalysisCard({ item, lang }: { item: AnalysisSummary; lang: "me" | "en" }) {
  const title = t(lang, item.title, item.title_mne || item.title);
  const summary = t(lang, item.summary, item.summary_mne || item.summary);
  const verdictLabel = t(
    lang,
    item.verdict_label,
    item.verdict_label_mne || item.verdict_label,
  );

  return (
    <Link to={`/analyses/${item.id}`}>
      <article className="group bg-card border border-border rounded-lg p-5 md:p-6 hover:border-primary/30 transition-all duration-300 cursor-pointer">
        <div className="flex gap-4 md:gap-6">
          <div className="flex-shrink-0">
            <div
              className={`w-12 h-12 md:w-14 md:h-14 rounded-full flex items-center justify-center text-lg md:text-xl font-bold font-body ${getScoreClass(item.decision_score)}`}
              style={{ color: "hsl(222, 30%, 8%)" }}
            >
              {item.decision_score != null ? `${item.decision_score}/10` : "—"}
            </div>
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="font-display text-base md:text-lg font-semibold text-card-foreground leading-snug mb-2 group-hover:text-primary transition-colors">
              {title}
            </h3>
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <time className="text-xs text-muted-foreground font-body">{item.date}</time>
              <span className="text-muted-foreground/40">&middot;</span>
              <span className={`text-xs font-medium uppercase tracking-wider ${getCategoryColor(item.category)}`}>
                {item.category}
              </span>
              {verdictLabel && (
                <>
                  <span className="text-muted-foreground/40">&middot;</span>
                  <span className={`text-xs font-medium px-2.5 py-0.5 rounded-full border ${getSentimentClasses(item.overall_verdict)}`}>
                    {verdictLabel}
                  </span>
                </>
              )}
            </div>
            <p className="text-sm text-muted-foreground leading-relaxed line-clamp-3">{summary}</p>
          </div>
        </div>
      </article>
    </Link>
  );
}
