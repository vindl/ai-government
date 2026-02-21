import ProseContent from "@/components/ProseContent";
import { usePageContent } from "@/hooks/usePageContent";
import { useLanguage } from "@/contexts/LanguageContext";
import { t } from "@/lib/i18n";

export default function Cabinet() {
  const { data, isLoading } = usePageContent("cabinet");
  const { lang } = useLanguage();

  return (
    <ProseContent title={t(lang, "Government Cabinet", "Kabinet")}>
      {isLoading && (
        <div className="space-y-4 animate-pulse">
          <div className="h-4 bg-muted rounded w-3/4" />
          <div className="h-4 bg-muted rounded w-full" />
          <div className="h-4 bg-muted rounded w-5/6" />
        </div>
      )}
      {data && (
        <div
          className="prose-content text-muted-foreground leading-relaxed text-sm md:text-base [&_h1]:font-display [&_h1]:text-2xl [&_h1]:font-bold [&_h1]:text-foreground [&_h1]:mt-10 [&_h1]:mb-4 [&_h2]:font-display [&_h2]:text-xl [&_h2]:font-bold [&_h2]:text-foreground [&_h2]:mt-8 [&_h2]:mb-3 [&_h3]:font-display [&_h3]:text-lg [&_h3]:font-bold [&_h3]:text-foreground [&_h3]:mt-6 [&_h3]:mb-2 [&_ol]:list-decimal [&_ol]:pl-6 [&_ol]:space-y-2 [&_ul]:list-disc [&_ul]:pl-6 [&_ul]:space-y-2 [&_p]:mb-4 [&_strong]:text-foreground [&_table]:w-full [&_table]:border-collapse [&_th]:border [&_th]:border-border [&_th]:bg-secondary [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:text-base [&_th]:font-semibold [&_th]:text-foreground [&_td]:border [&_td]:border-border [&_td]:px-4 [&_td]:py-3 [&_td]:text-base [&_td:nth-child(2)]:whitespace-nowrap [&_th:nth-child(2)]:whitespace-nowrap"
          dangerouslySetInnerHTML={{
            __html: lang === "en" ? data.en : data.mne,
          }}
        />
      )}
    </ProseContent>
  );
}
