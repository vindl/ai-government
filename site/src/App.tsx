import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { LanguageProvider } from "./contexts/LanguageContext";
import Layout from "./components/Layout";
import Index from "./pages/Index";
import AnalysisDetail from "./pages/AnalysisDetail";
import Constitution from "./pages/Constitution";
import Cabinet from "./pages/Cabinet";
import Challenges from "./pages/Challenges";
import Transparency from "./pages/Transparency";
import Architecture from "./pages/Architecture";
import News from "./pages/News";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <LanguageProvider>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter basename={import.meta.env.BASE_URL}>
          <Layout>
            <Routes>
              <Route path="/" element={<Index />} />
              <Route path="/analyses/:id" element={<AnalysisDetail />} />
              <Route path="/constitution" element={<Constitution />} />
              <Route path="/cabinet" element={<Cabinet />} />
              <Route path="/challenges" element={<Challenges />} />
              <Route path="/transparency" element={<Transparency />} />
              <Route path="/architecture" element={<Architecture />} />
              <Route path="/news" element={<News />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Layout>
        </BrowserRouter>
      </TooltipProvider>
    </LanguageProvider>
  </QueryClientProvider>
);

export default App;
