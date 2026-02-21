# Website Redesign — New React-Based Interface

The AI Government of Montenegro website has been completely redesigned. The previous static HTML site has been replaced with a modern single-page application built with React, TypeScript, and Tailwind CSS.

Key improvements:

- Bilingual support (English/Montenegrin) with a language toggle on every page
- Full analysis detail pages with ministry verdicts, score breakdowns, counter-proposals, and parliamentary debate transcripts
- Improved readability with a cleaner layout and consistent typography
- Faster navigation between pages without full page reloads
- Mobile-responsive design

The site continues to be statically generated — the Python build pipeline exports analysis data as JSON files, which the React app loads at runtime. No server-side infrastructure is required.
