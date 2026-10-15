/**
 * One Apple Health export import, from the upload to the nights being ready.
 * Used by Profile > Import and by Setup on a computer.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { ImportJob } from '../../api/client';
import { useApi } from '../../api/useApi';
import { errorText } from '../../lib/useLoad';

const MAX_BYTES = 2 * 1024 ** 3;
const RUNNING: ImportJob['state'][] = ['queued', 'running', 'processing'];

export type ImportProgress = {
  name: string;
  bytes: number;
  /** How much of the file has been sent, 0 to 1. */
  sent: number;
  /** The server's latest word on the import, once it has one. */
  status: ImportJob | null;
  /** Upload or connection problems. Problems reading the file come in status.error. */
  error: string | null;
};

/**
 * resume: pick up this person's import if one is still running (when the screen is reopened).
 * pollMs: how often to ask the server how it's going.
 */
export function useImportJob({ resume = false, pollMs = 1000 } = {}) {
  const api = useApi();
  const [job, setJob] = useState<ImportProgress | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mounted = useRef(true);

  const stop = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  };
  const patch = (changes: Partial<ImportProgress>) => setJob((j) => (j ? { ...j, ...changes } : j));

  /** Asks how the import is going until it's done. Rejects if it fails. */
  const follow = useCallback((importId: string) => new Promise<ImportJob>((resolve, reject) => {
    stop();
    const tick = async () => {
      try {
        const status = await api.importStatus(importId);
        if (!mounted.current) return;
        patch({ status });
        if (status.state === 'done') resolve(status);
        else if (status.state === 'error') reject(new Error(`Import failed: ${status.error}`));
        else timer.current = setTimeout(tick, pollMs);
      } catch (e) {
        if (mounted.current) patch({ error: errorText(e) });
        reject(e);
      }
    };
    timer.current = setTimeout(tick, pollMs);
  }), [api, pollMs]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      stop();
    };
  }, []);

  // Reopening the screen during an import picks it up again.
  useEffect(() => {
    if (!resume) return;
    api.imports().then(([s]) => {
      if (mounted.current && s && RUNNING.includes(s.state)) {
        setJob({ name: s.file_name, bytes: s.file_bytes, sent: 1, status: s, error: null });
        follow(s.import_id).catch(() => {});  // shown through job
      }
    }).catch(() => {});
  }, [api, resume, follow]);

  /** Uploads the file and follows the import. Resolves once the nights are ready. */
  async function start(file: File): Promise<ImportJob> {
    if (file.size > MAX_BYTES) {
      const error = 'That file is over 2 GB. Unzip it and pick export.xml, or use import_export.py on the server.';
      setJob({ name: file.name, bytes: file.size, sent: 0, status: null, error });
      throw new Error(error);
    }
    setJob({ name: file.name, bytes: file.size, sent: 0, status: null, error: null });
    let started: ImportJob;
    try {
      started = await api.importExport(file, file.name, (share) => patch({ sent: share }));
    } catch (e) {
      patch({ error: errorText(e) });
      throw e;
    }
    patch({ sent: 1 });
    return follow(started.import_id);
  }

  const state = job?.status?.state;
  return {
    job,
    start,
    busy: !!job && !job.error && state !== 'done' && state !== 'error',
    done: state === 'done',
  };
}

/**
 * The bar covers the whole job: sending the file (first 20%), the server reading it (to 95%),
 * then working out the nights.
 */
export function importProgress(job: ImportProgress): { share: number; phase: string } {
  const s = job.status;
  if (job.error || s?.state === 'error') return { share: 0, phase: 'Import failed' };
  if (!s) return { share: job.sent * 0.2, phase: 'Uploading' };
  if (s.state === 'queued') return { share: 0.2, phase: 'Reading the export' };
  if (s.state === 'running') {
    const what = s.reading && s.reading !== 'done' ? `${s.reading} records` : 'the export';
    return { share: 0.2 + s.read_fraction * 0.75, phase: `Reading ${what}` };
  }
  if (s.state === 'processing') return { share: 0.95, phase: 'Working out your nights' };
  return { share: 1, phase: 'Done' };
}
