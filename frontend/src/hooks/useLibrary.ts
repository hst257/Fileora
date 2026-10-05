import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Health, Job, Status, WatchStatus } from "../types";

export function useLibrary() {
  const [status, setStatus] = useState<Status>();
  const [health, setHealth] = useState<Health>();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState("");
  const [rootPath, setRootPath] = useState("");
  const [libraryBusy, setLibraryBusy] = useState(false);
  const [pendingWatch, setPendingWatch] = useState<boolean>();
  const [pendingMedia, setPendingMedia] = useState<boolean>();
  const [jobDetail, setJobDetail] = useState<Job>();
  const revision = useRef(0);
  const mounted = useRef(true);
  const indexing = jobs.some((job) =>
    ["queued", "running"].includes(job.state),
  );

  const refresh = useCallback(async () => {
    const request = ++revision.current;
    try {
      const [nextStatus, nextHealth, nextJobs] = await Promise.all([
        api<Status>("/index/status"),
        api<Health>("/health"),
        api<Job[]>("/jobs"),
      ]);
      if (!mounted.current || request !== revision.current) return;
      setStatus(nextStatus);
      setHealth(nextHealth);
      setJobs(nextJobs);
    } catch {
      if (mounted.current && request === revision.current) setHealth(undefined);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void refresh();
    return () => {
      mounted.current = false;
      ++revision.current;
    };
  }, [refresh]);

  useEffect(() => {
    const update = () => {
      if (!document.hidden) void refresh();
    };
    const timer = window.setInterval(update, indexing ? 1500 : 10000);
    document.addEventListener("visibilitychange", update);
    window.addEventListener("online", update);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", update);
      window.removeEventListener("online", update);
    };
  }, [indexing, refresh]);

  async function mutate(path: string, method: string, body?: unknown) {
    setLibraryBusy(true);
    setError("");
    try {
      await api(path, {
        method,
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
      await refresh();
      return true;
    } catch (err) {
      setError((err as Error).message);
      return false;
    } finally {
      setLibraryBusy(false);
    }
  }

  async function addRoot(event: React.FormEvent) {
    event.preventDefault();
    if (await mutate("/roots", "POST", { path: rootPath })) setRootPath("");
  }

  async function rescan(verify = false) {
    await mutate("/index/jobs", "POST", { verify });
  }

  async function setWatching(enabled: boolean) {
    setPendingWatch(enabled);
    setError("");
    try {
      const watch = await api<WatchStatus>("/index/watch", {
        method: "PUT",
        body: JSON.stringify({ enabled }),
      });
      setHealth((current) => (current ? { ...current, watch } : current));
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPendingWatch(undefined);
    }
  }

  async function setMedia(enabled: boolean) {
    setPendingMedia(enabled);
    setError("");
    try {
      await api("/index/media", {
        method: "PUT",
        body: JSON.stringify({ enabled }),
      });
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPendingMedia(undefined);
    }
  }

  async function forget(id: number) {
    if (
      !window.confirm(
        "Remove this folder from Fileora and forget its indexed content? Your original files will stay in place.",
      )
    )
      return false;
    return mutate(`/roots/${id}`, "DELETE");
  }

  async function inspectJob(job: Job) {
    setError("");
    try {
      setJobDetail(await api<Job>(`/jobs/${job.id}`));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function cancelJob(job: Job) {
    await mutate(`/jobs/${job.id}/cancel`, "POST");
  }

  return {
    status,
    health,
    jobs,
    indexing,
    error,
    setError,
    rootPath,
    setRootPath,
    libraryBusy,
    pendingWatch,
    pendingMedia,
    watchBusy: pendingWatch !== undefined,
    jobDetail,
    setJobDetail,
    refresh,
    addRoot,
    rescan,
    setWatching,
    setMedia,
    forget,
    inspectJob,
    cancelJob,
  };
}

export type LibraryState = ReturnType<typeof useLibrary>;
