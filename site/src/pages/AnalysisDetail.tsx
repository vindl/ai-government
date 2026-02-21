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

function ScoreBar({ score, label }: { score: number; label: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-muted-foreground w-40 shrink-0">{label}</span>
      <div className="flex-1 h-3 bg-secondary rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${getScoreClass(score)}`}
          style={{ width: `${score * 10}%` }}
        />
      </div>
      <span className="text-sm font-bold text-foreground w-10 text-right">{score}/10</span>
    </div>
  );
}

function Paragraphs({ text }: { text: string }) {
  const paragraphs = text.split(/\n+/).filter((s) => s.trim());
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
        {/* Critic headline + scores */}
        {critic_report && (
          <section>
            <h2 className="font-display text-lg font-bold text-foreground mb-2">
              {t(lang, critic_report.headline, critic_report.headline_mne || critic_report.headline)}
            </h2>
            <div className="space-y-3 mt-4">
              <ScoreBar
                score={critic_report.decision_score}
                label={t(lang, "Decision Quality", "Kvalitet odluke")}
              />
              <ScoreBar
                score={critic_report.assessment_quality_score}
                label={t(lang, "Assessment Quality", "Kvalitet procjene")}
              />
            </div>
          </section>
        )}

        {/* Ministry verdict cards */}
        {assessments.length > 0 && (
          <section>
            <h2 className="font-display text-xl md:text-2xl font-bold text-foreground mb-6 gold-underline pb-2 inline-block">
              {t(lang, "Ministry Assessments", "Ministarske procjene")}
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {assessments.map((a) => (
                <VerdictCard key={a.ministry} assessment={a} lang={lang} />
              ))}
            </div>
          </section>
        )}

        {/* Critic analysis */}
        {critic_report && (
          <section>
            <h2 className="font-display text-xl md:text-2xl font-bold text-foreground mb-4 gold-underline pb-2 inline-block">
              {t(lang, "Independent Critical Analysis", "Nezavisna kritička analiza")}
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

        {/* Unified counter-proposal */}
        {counter_proposal && (
          <section>
            <h2 className="font-display text-xl md:text-2xl font-bold text-foreground mb-4 gold-underline pb-2 inline-block">
              {t(lang, "Unified Counter-Proposal", "Jedinstveni kontraprijedlog")}
            </h2>
            <div className="p-5 bg-card border border-border rounded-lg space-y-4">
              <h3 className="font-display text-lg font-bold text-foreground">
                {t(lang, counter_proposal.title, counter_proposal.title_mne || counter_proposal.title)}
              </h3>
              <Paragraphs text={t(lang, counter_proposal.executive_summary, counter_proposal.executive_summary_mne || counter_proposal.executive_summary)} />

              <Paragraphs text={t(lang, counter_proposal.detailed_proposal, counter_proposal.detailed_proposal_mne || counter_proposal.detailed_proposal)} />

              {counter_proposal.key_differences.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-foreground mb-2">
                    {t(lang, "Key Differences", "Ključne razlike")}
                  </h4>
                  <ul className="list-disc pl-5 space-y-1">
                    {tList(lang, counter_proposal.key_differences, counter_proposal.key_differences_mne).map((d, i) => (
                      <li key={i} className="text-sm text-muted-foreground">{d}</li>
                    ))}
                  </ul>
                </div>
              )}

              {counter_proposal.implementation_steps.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-foreground mb-2">
                    {t(lang, "Implementation Steps", "Koraci implementacije")}
                  </h4>
                  <ol className="list-decimal pl-5 space-y-1">
                    {tList(lang, counter_proposal.implementation_steps, counter_proposal.implementation_steps_mne).map((s, i) => (
                      <li key={i} className="text-sm text-muted-foreground">{s}</li>
                    ))}
                  </ol>
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

        {/* Detailed ministry analyses */}
        {assessments.length > 0 && (
          <section>
            <h2 className="font-display text-xl md:text-2xl font-bold text-foreground mb-6 gold-underline pb-2 inline-block">
              {t(lang, "Detailed Ministry Analyses", "Detaljne analize ministarstava")}
            </h2>
            <div className="space-y-4">
              {assessments.map((a) => (
                <MinistryDetail key={a.ministry} assessment={a} lang={lang} />
              ))}
            </div>
          </section>
        )}

        {/* Parliamentary debate */}
        {debate && (
          <section>
            <h2 className="font-display text-xl md:text-2xl font-bold text-foreground mb-4 gold-underline pb-2 inline-block">
              {t(lang, "Parliamentary Debate", "Parlamentarna debata")}
            </h2>

            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <span className="text-sm text-muted-foreground">
                  {t(lang, "Overall verdict:", "Ukupni verdikt:")}
                </span>
                <span className={`text-sm font-semibold ${getVerdictColor(debate.overall_verdict)}`}>
                  {verdictLabel(debate.overall_verdict, lang)}
                </span>
              </div>

              <div>
                <h3 className="text-sm font-semibold text-foreground mb-2">
                  {t(lang, "Consensus", "Konsenzus")}
                </h3>
                <Paragraphs text={t(lang, debate.consensus_summary, debate.consensus_summary_mne || debate.consensus_summary)} />
              </div>

              {debate.disagreements.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-foreground mb-2">
                    {t(lang, "Points of Disagreement", "Tačke neslaganja")}
                  </h3>
                  <ul className="list-disc pl-5 space-y-1">
                    {tList(lang, debate.disagreements, debate.disagreements_mne).map((d, i) => (
                      <li key={i} className="text-sm text-muted-foreground">{d}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div>
                <h3 className="text-sm font-semibold text-foreground mb-2">
                  {t(lang, "Debate Transcript", "Transkript debate")}
                </h3>
                <div className="p-4 bg-card border border-border rounded-lg max-h-96 overflow-y-auto">
                  <Paragraphs text={t(lang, debate.debate_transcript, debate.debate_transcript_mne || debate.debate_transcript)} />
                </div>
              </div>
            </div>
          </section>
        )}
        </div>
      </div>
    </>
  );
}

function VerdictCard({ assessment, lang }: { assessment: Assessment; lang: "me" | "en" }) {
  const summaryText = t(
    lang,
    assessment.executive_summary || assessment.summary,
    assessment.executive_summary_mne || assessment.summary_mne || assessment.summary,
  );

  return (
    <div className={`p-4 rounded-lg border ${getVerdictBg(assessment.verdict)}`}>
      <div className="flex items-center justify-between mb-2">
        <span className="font-display font-bold text-foreground text-sm">
          {ministryName(assessment.ministry, lang)}
        </span>
        <div
          className={`w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold ${getScoreClass(assessment.score)}`}
          style={{ color: "hsl(222, 30%, 8%)" }}
        >
          {assessment.score}
        </div>
      </div>
      <span className={`text-xs font-medium ${getVerdictColor(assessment.verdict)}`}>
        {verdictLabel(assessment.verdict, lang)}
      </span>
      <p className="text-xs text-muted-foreground mt-2 line-clamp-3">{summaryText}</p>
    </div>
  );
}

function MinistryDetail({ assessment, lang }: { assessment: Assessment; lang: "me" | "en" }) {
  const [expanded, setExpanded] = useState(false);
  const summaryText = t(lang, assessment.summary, assessment.summary_mne || assessment.summary);

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full p-4 flex items-center justify-between hover:bg-secondary/30 transition-colors text-left"
      >
        <div className="flex items-center gap-3">
          <div
            className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold ${getScoreClass(assessment.score)}`}
            style={{ color: "hsl(222, 30%, 8%)" }}
          >
            {assessment.score}
          </div>
          <span className="font-display font-bold text-foreground text-sm">
            {ministryName(assessment.ministry, lang)}
          </span>
          <span className={`text-xs font-medium ${getVerdictColor(assessment.verdict)}`}>
            {verdictLabel(assessment.verdict, lang)}
          </span>
        </div>
        <svg
          className={`w-4 h-4 text-muted-foreground transition-transform ${expanded ? "rotate-180" : ""}`}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      {expanded && (
        <div className="p-4 border-t border-border space-y-4">
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

          {assessment.counter_proposal && (
            <div className="p-3 bg-secondary/40 rounded-lg">
              <h4 className="text-sm font-semibold text-foreground mb-2">
                {t(lang, "Counter-Proposal", "Kontraprijedlog")}: {t(lang, assessment.counter_proposal.title, assessment.counter_proposal.title_mne || assessment.counter_proposal.title)}
              </h4>
              <p className="text-sm text-muted-foreground mb-2">
                {t(lang, assessment.counter_proposal.summary, assessment.counter_proposal.summary_mne || assessment.counter_proposal.summary)}
              </p>
              {assessment.counter_proposal.key_changes.length > 0 && (
                <ul className="list-disc pl-5 space-y-1">
                  {tList(lang, assessment.counter_proposal.key_changes, assessment.counter_proposal.key_changes_mne).map((c, i) => (
                    <li key={i} className="text-xs text-muted-foreground">{c}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
