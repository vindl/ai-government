import ProseContent from "@/components/ProseContent";
import { useAnnouncements } from "@/hooks/useAnnouncements";
import { useLanguage } from "@/contexts/LanguageContext";
import { t } from "@/lib/i18n";

export default function News() {
  const { data: announcements, isLoading } = useAnnouncements();
  const { lang } = useLanguage();

  return (
    <ProseContent title={t(lang, "News", "Vijesti")}>
      {isLoading && (
        <div className="space-y-4 animate-pulse">
          <div className="p-6 bg-card border border-border rounded-lg">
            <div className="h-3 bg-muted rounded w-1/4 mb-4" />
            <div className="h-5 bg-muted rounded w-2/3 mb-4" />
            <div className="h-4 bg-muted rounded w-full mb-2" />
            <div className="h-4 bg-muted rounded w-5/6" />
          </div>
        </div>
      )}

      {announcements && announcements.length === 0 && (
        <p className="text-muted-foreground">
          {t(lang, "No announcements yet.", "Još nema objava.")}
        </p>
      )}

      {announcements && announcements.length > 0 && (
        <div className="space-y-6">
          {announcements.map((ann, i) => (
            <div key={i} className="p-6 bg-card border border-border rounded-lg">
              <div className="flex items-center gap-2 mb-4">
                <time className="text-xs text-muted-foreground font-body">{ann.date}</time>
              </div>
              <h2 className="font-display text-xl md:text-2xl font-bold text-foreground mb-4">
                {lang === "en" ? ann.title : ann.title_mne}
              </h2>
              <div
                className="space-y-4 text-sm text-muted-foreground leading-relaxed [&_p]:mb-3 [&_strong]:text-foreground [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:list-decimal [&_ol]:pl-6"
                dangerouslySetInnerHTML={{
                  __html: lang === "en" ? ann.html : ann.html_mne,
                }}
              />
            </div>
          ))}
        </div>
      )}
    </ProseContent>
  );
}
