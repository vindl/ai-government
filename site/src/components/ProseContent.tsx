export default function ProseContent({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <>
      <section className="hero-gradient px-6 md:px-12 lg:px-16 py-16 md:py-20 border-b border-border">
        <div className="max-w-3xl">
          <h1 className="font-display text-3xl md:text-4xl lg:text-5xl font-bold text-foreground leading-tight">
            {title}
          </h1>
        </div>
      </section>

      <section className="px-6 md:px-12 lg:px-16 py-12">
        <div className="max-w-3xl prose-content">{children}</div>
      </section>
    </>
  );
}
