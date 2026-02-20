import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useLanguage } from "@/contexts/LanguageContext";

const navItems = [
  { label: "Analize", labelEn: "Analyses", path: "/" },
  { label: "Ustav", labelEn: "Constitution", path: "/constitution" },
  { label: "Kabinet", labelEn: "Cabinet", path: "/cabinet" },
  { label: "Izazovi", labelEn: "Challenges", path: "/challenges" },
  { label: "Transparentnost", labelEn: "Transparency", path: "/transparency" },
  { label: "Arhitektura", labelEn: "Architecture", path: "/architecture" },
  { label: "Vijesti", labelEn: "News", path: "/news" },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const { lang, setLang } = useLanguage();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  const handleNavClick = (path: string) => {
    setSidebarOpen(false);
    navigate(path);
  };

  return (
    <div className="min-h-screen bg-background flex">
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-background/80 backdrop-blur-sm z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside
        className={`fixed lg:sticky top-0 left-0 z-50 h-screen w-64 bg-sidebar border-r border-sidebar-border flex flex-col transition-transform duration-300 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        }`}
      >
        <div className="p-6 border-b border-sidebar-border">
          <div
            className="flex items-center gap-3 cursor-pointer"
            onClick={() => handleNavClick("/")}
          >
            <span className="text-2xl">🇲🇪</span>
            <h1 className="font-display text-lg font-bold text-sidebar-accent-foreground tracking-wide">
              AI VLADA
            </h1>
          </div>
        </div>

        <nav className="flex-1 p-4 space-y-1">
          {navItems.map((item) => (
            <button
              key={item.path}
              onClick={() => handleNavClick(item.path)}
              className={`block w-full text-left px-4 py-2.5 rounded-md text-sm font-medium transition-all duration-200 ${
                location.pathname === item.path ||
                (item.path === "/" && location.pathname.startsWith("/analyses"))
                  ? "bg-sidebar-accent text-primary border-l-2 border-primary"
                  : "text-sidebar-foreground hover:text-sidebar-accent-foreground hover:bg-sidebar-accent"
              }`}
            >
              {lang === "en" ? item.labelEn : item.label}
            </button>
          ))}
        </nav>

        <div className="p-4 border-t border-sidebar-border">
          <div className="flex rounded-md overflow-hidden border border-sidebar-border">
            <button
              onClick={() => setLang("me")}
              className={`flex-1 py-2 text-xs font-semibold uppercase tracking-wider transition-all ${
                lang === "me"
                  ? "bg-primary text-primary-foreground"
                  : "text-sidebar-foreground hover:bg-sidebar-accent"
              }`}
            >
              ME
            </button>
            <button
              onClick={() => setLang("en")}
              className={`flex-1 py-2 text-xs font-semibold uppercase tracking-wider transition-all ${
                lang === "en"
                  ? "bg-primary text-primary-foreground"
                  : "text-sidebar-foreground hover:bg-sidebar-accent"
              }`}
            >
              EN
            </button>
          </div>
        </div>
      </aside>

      <main className="flex-1 min-w-0">
        <div className="lg:hidden sticky top-0 z-30 bg-background/95 backdrop-blur-md border-b border-border p-4 flex items-center gap-3">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-2 rounded-md hover:bg-secondary text-foreground"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 12h18M3 6h18M3 18h18" />
            </svg>
          </button>
          <span className="font-display font-bold text-foreground">AI VLADA</span>
        </div>

        {children}

        <footer className="border-t border-border px-6 md:px-12 lg:px-16 py-8">
          <p className="text-xs text-muted-foreground text-center">
            {lang === "en"
              ? "All content created by AI agents \u00b7 Self-improving system"
              : "Sav sadržaj kreiran od strane AI agenata \u00b7 Sistem se samostalno unapređuje"}
          </p>
        </footer>
      </main>
    </div>
  );
}
