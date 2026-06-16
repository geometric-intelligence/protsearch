export default function PageBackground({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="relative min-h-screen bg-page">
      <div className="relative">{children}</div>
    </div>
  );
}
