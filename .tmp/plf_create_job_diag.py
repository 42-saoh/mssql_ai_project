from __future__ import annotations

import os

from api_app.platform_db import MssqlPlatformRepository, PlatformDbSettings


def debug_execute(self: MssqlPlatformRepository, sql: str, params: tuple[object, ...]) -> None:
    connection = self._connect()
    try:
        cursor = connection.cursor()
        cursor.execute(sql, params)
        print("EXEC_OK", " ".join(sql.split())[:160])
    except Exception as exc:  # noqa: BLE001 - diagnostic script
        print("EXEC_FAIL", " ".join(sql.split())[:300])
        print("ERROR_TYPE", type(exc).__name__)
        print("ERROR", str(exc)[:1000])
        raise
    finally:
        connection.close()


def debug_query_all(
    self: MssqlPlatformRepository,
    sql: str,
    params: tuple[object, ...],
) -> list[tuple[object, ...]]:
    connection = self._connect()
    try:
        cursor = connection.cursor()
        cursor.execute(sql, params)
        rows = list(cursor.fetchall())
        print("QUERY_OK", " ".join(sql.split())[:160], "rows", len(rows))
        return rows
    except Exception as exc:  # noqa: BLE001 - diagnostic script
        print("QUERY_FAIL", " ".join(sql.split())[:300])
        print("ERROR_TYPE", type(exc).__name__)
        print("ERROR", str(exc)[:1000])
        raise
    finally:
        connection.close()


def main() -> None:
    settings = PlatformDbSettings(
        host=os.environ["PLATFORM_DB_HOST"],
        port=int(os.environ["PLATFORM_DB_PORT"]),
        user=os.environ["PLATFORM_DB_USER"],
        password=os.environ["PLATFORM_DB_PASSWORD"],
        database=os.environ["PLATFORM_DB_NAME"],
        requester_login=os.environ.get("PLATFORM_DB_REQUESTER_LOGIN", "codex-api-local"),
        connect_timeout_seconds=int(os.environ.get("PLATFORM_DB_CONNECT_TIMEOUT_SECONDS", "10")),
    )
    repository = MssqlPlatformRepository(settings)
    repository._execute = debug_execute.__get__(repository, MssqlPlatformRepository)  # type: ignore[method-assign]
    repository._query_all = debug_query_all.__get__(repository, MssqlPlatformRepository)  # type: ignore[method-assign]
    job = repository.create_job(os.environ["DIAG_REQUEST_ID"], correlation_id="diag-create-job")
    print("JOB_OK", job.job_id, job.target_key)


if __name__ == "__main__":
    main()
