// @ts-nocheck
import { useEffect, useState } from 'react';

/** @param {() => Promise<any>} loader @param {unknown[]} deps */
export function useLoad(loader, deps) {
  const [state, setState] = useState(/** @type {{ status: 'loading'|'error'|'ready', data: any, error: string }} */ ({ status: 'loading', data: null, error: '' }));
  useEffect(() => {
    let live = true;
    setState({ status: 'loading', data: null, error: '' });
    loader()
      .then((data) => { if (live) setState({ status: 'ready', data, error: '' }); })
      .catch((reason) => { if (live) setState({ status: 'error', data: null, error: reason instanceof Error ? reason.message : 'Something went wrong. Please try again.' }); });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}
