import { useParams, Link } from "react-router-dom";
import { useState } from "react";
import { useAnalysis } from "@/hooks/useAnalysis";
import { useLanguage } from "@/contexts/LanguageContext";
import { t, tList } from "@/lib/i18n";
import type { Assessment, Verdict, SessionResult } from "@/types";

const VERDICT_LABELS: Record<string, string> = {
  strongly_positive: "Strongly Positive",
  positive: "Positive",
  neutral: "Neutral",
  negative: "Negative",
  strongly_negative: "Strongly Negative",
};

const VERDICT_LABELS_MNE: Record<string, string> = {
  strongly_positive: "Izrazito pozitivno",
  positive: "Pozitivno",
  neutral: "Neutralno",
  negative: "Negativno",
  strongly_negative: "Izrazito negativno",
};

const MINISTRY_NAMES_MNE: Record<string, string> = {
  Finance: "Finansije",
  Justice: "Pravda",
  "EU Integration": "Evropske integracije",
  Health: "Zdravlje",
  Interior: "Unutrašnji poslovi",
  Education: "Prosvjeta",
  Economy: "Ekonomija",
  Tourism: "Turizam",
  Environment: "Životna sredina",
  Labour: "Rad",
};

function verdictLabel(verdict: Verdict | string, lang: "me" | "en"): string {
  return lang === "en"
    ? VERDICT_LABELS[verdict] || verdict
    : VERDICT_LABELS_MNE[verdict] || verdict;
}

function ministryName(name: string, lang: "me" | "en"): string {
  return lang === "me" ? MINISTRY_NAMES_MNE[name] || name : name;
}

function getVerdictColor(verdict: Verdict | string): string {
  switch (verdict) {
    case "strongly_positive":
    case "positive":
      return "text-sentiment-positive";
    case "negative":
      return "text-sentiment-negative";
    case "strongly_negative":
      return "text-sentiment-strongly-negative";
    default:
      return "text-sentiment-neutral";
  }
}

function getVerdictBg(verdict: Verdict | string): string {
  switch (verdict) {
    case "strongly_positive":
    case "positive":
      return "bg-sentiment-positive/15 border-sentiment-positive/30";
    case "negative":
      return "bg-sentiment-negative/15 border-sentiment-negative/30";
    case "strongly_negative":
      return "bg-sentiment-strongly-negative/15 border-sentiment-strongly-negative/30";
    default:
      return "bg-sentiment-neutral/15 border-sentiment-neutral/30";
  }
}

function getScoreClass(score: number) {
  if (score >= 7) return "score-gradient-high";
  if (score >= 4) return "score-gradient-mid";
  return "score-gradient-low";
}

/**
 * Split a block of text that has no newlines into ~3-sentence paragraphs.
 * Handles ". " as the primary sentence boundary while avoiding false splits
 * on common abbreviations (e.g., "EU.", "No.", "Ch.").
 */
function splitIntoParagraphs(text: string, sentencesPerParagraph = 3): string[] {
  // Split on sentence-ending periods followed by a space and an uppercase letter.
  // This avoids splitting on abbreviations like "e.g." or "Ch.23".
  const sentences = text.split(/(?<=\.)\s+(?=[A-ZČĆŽŠĐ])/);
  if (sentences.length <= sentencesPerParagraph) return [text];
  const paragraphs: string[] = [];
  for (let i = 0; i < sentences.length; i += sentencesPerParagraph) {
    paragraphs.push(sentences.slice(i, i + sentencesPerParagraph).join(" "));
  }
  return paragraphs;
}

function Paragraphs({ text }: { text: string }) {
  let paragraphs = text.split(/\n+/).filter((s) => s.trim());
  // If the text has no newlines (single block), split into readable paragraphs
  if (paragraphs.length <= 1 && text.length > 300) {
    paragraphs = splitIntoParagraphs(text.trim());
  }
  if (paragraphs.length <= 1) {
    return <p className="text-sm text-muted-foreground leading-relaxed">{text}</p>;
  }
  return (
    <>
      {paragraphs.map((p, i) => (
        <p key={i} className="text-sm text-muted-foreground leading-relaxed mb-4">{p}</p>
      ))}
    </>
  );
}

function ScoreCircle({ score, label }: { score: number; label: string }) {
  return (
    <div className="flex flex-col items-center gap-2">
      <div
        className={`w-20 h-20 rounded-full flex items-center justify-center text-2xl font-bold ${getScoreClass(score)}`}
        style={{ color: "hsl(222, 30%, 8%)" }}
      >
        {score}/10
      </div>
      <span className="text-xs text-muted-foreground text-center">{label}</span>
    </div>
  );
}

export default function AnalysisDetail() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading, error } = useAnalysis(id);
  const { lang } = useLanguage();

  if (isLoading) {
    return (
      <div className="content-width py-16">
        <div className="animate-pulse space-y-6">
          <div className="h-8 bg-muted rounded w-3/4" />
          <div className="h-4 bg-muted rounded w-1/3" />
          <div className="h-24 bg-muted rounded" />
          <div className="grid grid-cols-2 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-32 bg-muted rounded" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="content-width py-16">
        <h1 className="font-display text-3xl font-bold text-foreground mb-4">
          {t(lang, "Analysis not found", "Analiza nije pronađena")}
        </h1>
        <Link to="/" className="text-primary hover:underline">
          &larr; {t(lang, "Back to analyses", "Nazad na analize")}
        </Link>
      </div>
    );
  }

  return <AnalysisContent data={data} lang={lang} />;
}

function AnalysisContent({ data, lang }: { data: SessionResult; lang: "me" | "en" }) {
  const { decision, assessments, critic_report, counter_proposal, debate } = data;

  const title = t(lang, decision.title, decision.title_mne || decision.title);
  const summary = t(lang, decision.summary, decision.summary_mne || decision.summary);
  const repoUrl = "https://github.com/vindl/ai-government";

  return (
    <>
      {/* Header */}
      <section className="hero-gradient py-8 md:py-12 border-b border-border">
        <div className="content-width">
          <Link to="/" className="text-sm text-muted-foreground hover:text-primary transition-colors mb-4 inline-block">
            &larr; {t(lang, "All analyses", "Sve analize")}
          </Link>
          <h1 className="font-display text-2xl md:text-3xl lg:text-4xl font-bold text-foreground leading-tight mb-4">
            {title}
          </h1>
          <div className="flex flex-wrap items-center gap-3 mb-6">
            <time className="text-sm text-muted-foreground">{decision.date}</time>
            <span className="text-muted-foreground/40">&middot;</span>
            <span className="text-sm font-medium uppercase tracking-wider text-primary">{decision.category}</span>
            {decision.source_url && (
              <>
                <span className="text-muted-foreground/40">&middot;</span>
                <a href={decision.source_url} target="_blank" rel="noopener noreferrer" className="text-sm text-primary hover:underline">
                  {t(lang, "Source", "Izvor")} &rarr;
                </a>
              </>
            )}
          </div>
          <blockquote className="border-l-2 border-primary pl-4 italic text-muted-foreground text-sm leading-relaxed">
            {summary}
          </blockquote>
        </div>
      </section>

      <div className="py-10">
        <div className="content-width space-y-12">

          {/* Scores */}
          {critic_report && (
            <section>
              <h2 className="font-display text-lg font-bold text-foreground mb-6">
                {t(lang, critic_report.headline, critic_report.headline_mne || critic_report.headline)}
              </h2>
              <div className="flex items-center justify-center gap-12 md:gap-20 py-4">
                <ScoreCircle
                  score={critic_report.decision_score}
                  label={t(lang, "Government Decision", "Odluka vlade")}
                />
                <div className="text-2xl text-muted-foreground/30 font-light">vs</div>
                <ScoreCircle
                  score={critic_report.assessment_quality_score}
                  label={t(lang, "AI Analysis", "AI analiza")}
                />
              </div>
            </section>
          )}

          {/* Ministry Assessments — expandable cards (merged summary + detail) */}
          {assessments.length > 0 && (
            <section>
              <h2 className="font-display text-xl md:text-2xl font-bold text-foreground mb-6 gold-underline pb-2 inline-block">
                {t(lang, "Ministry Assessments", "Ministarske procjene")}
              </h2>
              <div className="space-y-3">
                {assessments.map((a) => (
                  <MinistryCard key={a.ministry} assessment={a} lang={lang} />
                ))}
              </div>
            </section>
          )}

          {/* Critical Analysis */}
          {critic_report && (
            <section>
              <h2 className="font-display text-xl md:text-2xl font-bold text-foreground mb-4 gold-underline pb-2 inline-block">
                {t(lang, "Critical Analysis", "Kritička analiza")}
              </h2>
              <Paragraphs text={t(lang, critic_report.overall_analysis, critic_report.overall_analysis_mne || critic_report.overall_analysis)} />

              {critic_report.blind_spots.length > 0 && (
                <div className="mt-4">
                  <h3 className="text-sm font-semibold text-foreground mb-2">
                    {t(lang, "Blind Spots", "Slijepe tačke")}
                  </h3>
                  <ul className="list-disc pl-5 space-y-1">
                    {tList(lang, critic_report.blind_spots, critic_report.blind_spots_mne).map((bs, i) => (
                      <li key={i} className="text-sm text-muted-foreground">{bs}</li>
                    ))}
                  </ul>
                </div>
              )}

              {critic_report.eu_chapter_relevance.length > 0 && (
                <div className="mt-4">
                  <h3 className="text-sm font-semibold text-foreground mb-2">
                    {t(lang, "EU Chapter Relevance", "Relevantnost poglavlja EU")}
                  </h3>
                  <ul className="list-disc pl-5 space-y-1">
                    {critic_report.eu_chapter_relevance.map((ch, i) => (
                      <li key={i} className="text-sm text-muted-foreground">{ch}</li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          )}

          {/* Counter-Proposal */}
          {counter_proposal && (
            <section>
              <h2 className="font-display text-xl md:text-2xl font-bold text-foreground mb-4 gold-underline pb-2 inline-block">
                {t(lang, "AI Counter-Proposal", "AI kontraprijedlog")}
              </h2>
              <div className="p-5 bg-card border border-border rounded-lg space-y-4">
                <h3 className="font-display text-lg font-bold text-foreground">
                  {t(lang, counter_proposal.title, counter_proposal.title_mne || counter_proposal.title)}
                </h3>
                <Paragraphs text={t(lang, counter_proposal.executive_summary, counter_proposal.executive_summary_mne || counter_proposal.executive_summary)} />

                {counter_proposal.key_differences.length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold text-foreground mb-2">
                      {t(lang, "Key Differences from Government", "Ključne razlike od vladine odluke")}
                    </h4>
                    <ul className="list-disc pl-5 space-y-1">
                      {tList(lang, counter_proposal.key_differences, counter_proposal.key_differences_mne).map((d, i) => (
                        <li key={i} className="text-sm text-muted-foreground">{d}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {counter_proposal.risks_and_tradeoffs.length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold text-foreground mb-2">
                      {t(lang, "Risks & Trade-offs", "Rizici i kompromisi")}
                    </h4>
                    <ul className="list-disc pl-5 space-y-1">
                      {tList(lang, counter_proposal.risks_and_tradeoffs, counter_proposal.risks_and_tradeoffs_mne).map((r, i) => (
                        <li key={i} className="text-sm text-muted-foreground">{r}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </section>
          )}

          {/* Full transcript link */}
          <section className="border-t border-border pt-8">
            <p className="text-sm text-muted-foreground">
              {t(
                lang,
                "This analysis includes parliamentary debate, detailed ministry reasoning, implementation steps, and individual counter-proposals.",
                "Ova analiza uključuje parlamentarnu debatu, detaljno obrazloženje ministarstava, korake implementacije i pojedinačne kontraprijedloge.",
              )}{" "}
              <a
                href={data.issue_number
                  ? `${repoUrl}/issues/${data.issue_number}`
                  : `${repoUrl}/issues?q=is%3Aissue+label%3Atask%3Aanalysis+%22${encodeURIComponent(decision.title)}%22`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline"
              >
                {t(lang, "View full transcript", "Pogledaj kompletan transkript")} &rarr;
              </a>
            </p>
          </section>

        </div>
      </div>
    </>
  );
}

function MinistryCard({ assessment, lang }: { assessment: Assessment; lang: "me" | "en" }) {
  const [expanded, setExpanded] = useState(false);
  const summaryText = t(
    lang,
    assessment.executive_summary || assessment.summary,
    assessment.executive_summary_mne || assessment.summary_mne || assessment.summary,
  );

  return (
    <div className={`rounded-lg border overflow-hidden ${getVerdictBg(assessment.verdict)}`}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full p-4 flex items-center justify-between hover:bg-white/5 transition-colors text-left"
      >
        <div className="flex items-center gap-3">
          <div
            className={`w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${getScoreClass(assessment.score)}`}
            style={{ color: "hsl(222, 30%, 8%)" }}
          >
            {assessment.score}
          </div>
          <span className="font-bold text-foreground text-sm">
            {ministryName(assessment.ministry, lang)}
          </span>
          <span className={`text-xs font-medium ${getVerdictColor(assessment.verdict)}`}>
            {verdictLabel(assessment.verdict, lang)}
          </span>
        </div>
        <svg
          className={`w-4 h-4 text-muted-foreground transition-transform shrink-0 ${expanded ? "rotate-180" : ""}`}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-4">
          <Paragraphs text={summaryText} />

          {assessment.key_concerns.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-foreground mb-2">
                {t(lang, "Key Concerns", "Ključne brige")}
              </h4>
              <ul className="list-disc pl-5 space-y-1">
                {tList(lang, assessment.key_concerns, assessment.key_concerns_mne).map((c, i) => (
                  <li key={i} className="text-sm text-muted-foreground">{c}</li>
                ))}
              </ul>
            </div>
          )}

          {assessment.recommendations.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-foreground mb-2">
                {t(lang, "Recommendations", "Preporuke")}
              </h4>
              <ul className="list-disc pl-5 space-y-1">
                {tList(lang, assessment.recommendations, assessment.recommendations_mne).map((r, i) => (
                  <li key={i} className="text-sm text-muted-foreground">{r}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
