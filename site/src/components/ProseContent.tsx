export default function ProseContent({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <>
      <section className="hero-gradient py-8 md:py-12 border-b border-border">
        <div className="content-width">
          <h1 className="font-display text-3xl md:text-4xl lg:text-5xl font-bold text-foreground leading-tight">
            {title}
          </h1>
        </div>
      </section>

      <section className="py-12">
        <div className="content-width">{children}</div>
      </section>
    </>
  );
}
