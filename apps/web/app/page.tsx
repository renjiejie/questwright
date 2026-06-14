import Link from "next/link";

export default function HomePage() {
  return (
    <main>
      <h1>Questwright</h1>
      <p>Phase 0 placeholder. Workflow UI will live here.</p>
      <nav>
        <ul>
          <li>
            <Link href="/knowledge">Knowledge 检索调试</Link>
          </li>
        </ul>
      </nav>
    </main>
  );
}
