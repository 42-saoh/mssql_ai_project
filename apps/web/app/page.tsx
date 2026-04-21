export default function HomePage() {
  return (
    <main style={{ maxWidth: 960, margin: "0 auto", padding: "48px 24px" }}>
      <h1>MSSQL 분석·문서화·전환코드 생성 Agent 플랫폼</h1>
      <p>
        중앙 포털의 최소 스타터 화면입니다. 다음 단계에서는 요청 등록, 작업 상태, 산출물
        미리보기, 승인/반려 화면을 연결합니다.
      </p>

      <section>
        <h2>현재 연결된 축</h2>
        <ul>
          <li>API/BFF skeleton</li>
          <li>MSSQL Metadata MCP skeleton</li>
          <li>OpenAPI / DDL / validation spec 초안</li>
          <li>Codex agents / skills / policy docs</li>
        </ul>
      </section>
    </main>
  );
}
