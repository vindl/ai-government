import ProseContent from "@/components/ProseContent";
import { useTransparency } from "@/hooks/useTransparency";
import { useLanguage } from "@/contexts/LanguageContext";
import { t } from "@/lib/i18n";
import type { Intervention } from "@/types";

function getTypeLabel(type: string, lang: "me" | "en") {
  switch (type) {
    case "pr_merge":
      return t(lang, "Human-authored PR", "PR kreiran od strane čovjeka");
    case "suggestion":
      return t(lang, "Human-filed task", "Zadatak koji je odredio čovjek");
    case "override":
      return "HUMAN OVERRIDE";
    default:
      return type;
  }
}

function getTypeClasses(type: string) {
  switch (type) {
    case "pr_merge":
      return "bg-primary/15 text-primary border-primary/30";
    case "suggestion":
      return "bg-score-high/15 text-score-high border-score-high/30";
    case "override":
      return "bg-destructive/15 text-destructive border-destructive/30";
    default:
      return "bg-muted text-muted-foreground border-border";
  }
}

function getTitle(item: Intervention): string {
  return item.issue_title || item.pr_title || "";
}

function getRef(item: Intervention): string {
  if (item.pr_number) return `#${item.pr_number}`;
  if (item.issue_number) return `#${item.issue_number}`;
  return "";
}

export default function Transparency() {
  const { data, isLoading } = useTransparency();
  const { lang } = useLanguage();

  return (
    <ProseContent title={t(lang, "Human Influence Transparency Report", "Izvještaj o transparentnosti ljudskog uticaja")}>
      <p className="text-muted-foreground leading-relaxed mb-4">
        {t(
          lang,
          "This project operates under a Constitution that mandates full transparency. AI does not operate unsupervised \u2014 humans intervene when necessary, and every intervention is a public record.",
          "Ovaj projekat funkcioniše po Ustavu koji zahtijeva potpunu transparentnost. AI ne radi bez nadzora \u2014 ljudi intervenišu kada je potrebno, a svaka intervencija je javni zapis.",
        )}
      </p>

      <div className="p-4 bg-secondary/60 border border-border rounded-lg mb-8">
        <h3 className="text-sm font-semibold text-foreground mb-2">
          {t(lang, "Three types of human influence:", "Tri vrste ljudskog uticaja:")}
        </h3>
        <ol className="list-decimal pl-5 text-sm text-muted-foreground space-y-1">
          <li>
            <strong>{t(lang, "Overrides:", "Zamjene:")}</strong>{" "}
            {t(
              lang,
              "When AI triage rejects a proposal, a human can reopen the issue using HUMAN OVERRIDE.",
              "Kada AI trijaža odbije prijedlog, čovjek može ponovo otvoriti pitanje koristeći HUMAN OVERRIDE.",
            )}
          </li>
          <li>
            <strong>{t(lang, "Tasks:", "Zadaci:")}</strong>{" "}
            {t(
              lang,
              "Issues directly filed by humans, directing AI to work on specific tasks.",
              "Pitanja direktno kreirana od strane ljudi, koja usmjeravaju AI da radi na određenim zadacima.",
            )}
          </li>
          <li>
            <strong>{t(lang, "PRs:", "PR-ovi:")}</strong>{" "}
            {t(
              lang,
              "Pull requests initiated and authored by a human.",
              "Pull zahtjevi koje je čovjek inicirao i napisao.",
            )}
          </li>
        </ol>
      </div>

      {isLoading && (
        <div className="space-y-3 animate-pulse">
          {[1, 2, 3].map((i) => (
            <div key={i} className="p-4 bg-card border border-border rounded-lg">
              <div className="h-3 bg-muted rounded w-1/3 mb-2" />
              <div className="h-4 bg-muted rounded w-2/3" />
            </div>
          ))}
        </div>
      )}

      {data && (
        <>
          <p className="text-sm text-muted-foreground mb-6">
            <strong className="text-foreground">
              {t(lang, "Total recorded interventions:", "Ukupno zabilježenih intervencija:")}
            </strong>{" "}
            <span className="text-primary font-bold">{data.total}</span>
          </p>

          <div className="space-y-3">
            {data.interventions.map((item, i) => (
              <div key={i} className="p-4 bg-card border border-border rounded-lg hover:border-primary/30 transition-colors">
                <div className="flex flex-wrap items-center gap-2 mb-2">
                  <time className="text-xs text-muted-foreground font-body">
                    {item.timestamp.slice(0, 10)}
                  </time>
                  <span className="text-muted-foreground/40">&middot;</span>
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${getTypeClasses(item.type)}`}>
                    {getTypeLabel(item.type, lang)}
                  </span>
                  {getRef(item) && (
                    <span className="text-xs text-muted-foreground">{getRef(item)}</span>
                  )}
                </div>
                <p className="text-sm text-foreground font-medium">{getTitle(item)}</p>
              </div>
            ))}
          </div>
        </>
      )}
    </ProseContent>
  );
}
