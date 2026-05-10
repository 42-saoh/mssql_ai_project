export function DependencyBlocker({
  title,
  message,
  code = "PORTAL_API_CONFIGURATION_BLOCKED",
}: Readonly<{
  title: string;
  message: string;
  code?: string;
}>) {
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Dependency blocker</p>
          <h1>{title}</h1>
        </div>
        <span className="quiet-label">{code}</span>
      </div>
      <div className="blocker-list">
        <article className="blocker-row">
          <strong>{code}</strong>
          <span>{message}</span>
        </article>
      </div>
    </section>
  );
}
