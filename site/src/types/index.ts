/** Mirrors Python Verdict enum */
export type Verdict =
  | "strongly_positive"
  | "positive"
  | "neutral"
  | "negative"
  | "strongly_negative";

/** Summary object in analyses-index.json */
export interface AnalysisSummary {
  id: string;
  title: string;
  title_mne: string;
  summary: string;
  summary_mne: string;
  date: string;
  category: string;
  source_url: string;
  decision_score: number | null;
  headline: string;
  headline_mne: string;
  overall_verdict: Verdict | null;
  verdict_label: string;
  verdict_label_mne: string;
  issue_number: number | null;
}

/** Mirrors Python GovernmentDecision */
export interface GovernmentDecision {
  id: string;
  title: string;
  summary: string;
  full_text: string;
  date: string;
  source_url: string;
  category: string;
  tags: string[];
  title_mne: string;
  summary_mne: string;
}

/** Mirrors Python MinistryCounterProposal */
export interface MinistryCounterProposal {
  title: string;
  summary: string;
  key_changes: string[];
  expected_benefits: string[];
  estimated_feasibility: string;
  title_mne: string;
  summary_mne: string;
  key_changes_mne: string[];
  expected_benefits_mne: string[];
  estimated_feasibility_mne: string;
}

/** Mirrors Python Assessment */
export interface Assessment {
  ministry: string;
  decision_id: string;
  verdict: Verdict;
  score: number;
  summary: string;
  executive_summary: string | null;
  reasoning: string;
  key_concerns: string[];
  recommendations: string[];
  counter_proposal: MinistryCounterProposal | null;
  summary_mne: string;
  executive_summary_mne: string | null;
  key_concerns_mne: string[];
  recommendations_mne: string[];
}

/** Mirrors Python ParliamentDebate */
export interface ParliamentDebate {
  decision_id: string;
  consensus_summary: string;
  disagreements: string[];
  overall_verdict: Verdict;
  debate_transcript: string;
  consensus_summary_mne: string;
  disagreements_mne: string[];
  debate_transcript_mne: string;
}

/** Mirrors Python CounterProposal */
export interface CounterProposal {
  decision_id: string;
  title: string;
  executive_summary: string;
  detailed_proposal: string;
  ministry_contributions: string[];
  key_differences: string[];
  implementation_steps: string[];
  risks_and_tradeoffs: string[];
  title_mne: string;
  executive_summary_mne: string;
  detailed_proposal_mne: string;
  ministry_contributions_mne: string[];
  key_differences_mne: string[];
  implementation_steps_mne: string[];
  risks_and_tradeoffs_mne: string[];
}

/** Mirrors Python CriticReport */
export interface CriticReport {
  decision_id: string;
  decision_score: number;
  assessment_quality_score: number;
  blind_spots: string[];
  overall_analysis: string;
  headline: string;
  eu_chapter_relevance: string[];
  headline_mne: string;
  overall_analysis_mne: string;
  blind_spots_mne: string[];
}

/** Full analysis result — mirrors Python SessionResult */
export interface SessionResult {
  decision: GovernmentDecision;
  assessments: Assessment[];
  debate: ParliamentDebate | null;
  critic_report: CriticReport | null;
  counter_proposal: CounterProposal | null;
  issue_number: number | null;
}

/** Bilingual page content (constitution, architecture, etc.) */
export interface PageContent {
  en: string;
  mne: string;
}

/** Transparency intervention item */
export interface Intervention {
  type: "override" | "suggestion" | "pr_merge";
  timestamp: string;
  issue_number?: number;
  pr_number?: number;
  issue_title?: string;
  pr_title?: string;
  actor?: string;
  creator?: string;
  status?: string;
  ai_verdict?: string;
  human_action?: string;
  rationale?: string;
}

export interface TransparencyData {
  interventions: Intervention[];
  total: number;
}

/** Announcement item */
export interface Announcement {
  date: string;
  title: string;
  html: string;
  title_mne: string;
  html_mne: string;
}
