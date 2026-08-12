import { SparklesIcon } from '@heroicons/react/24/outline';

/** Lightweight auth loading surface — avoid heavy framer stacks on every route gate. */
const LoadingScreen = () => {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-100 flex items-center justify-center">
      <div className="relative z-10 text-center px-6">
        <div className="relative mx-auto w-20 h-20 mb-6">
          <div className="absolute inset-0 rounded-full bg-gradient-to-r from-primary-500 via-secondary-500 to-accent-500 p-1 animate-spin [animation-duration:3s]">
            <div className="w-full h-full bg-white rounded-full flex items-center justify-center">
              <SparklesIcon className="w-9 h-9 text-primary-600" />
            </div>
          </div>
        </div>

        <h1 className="text-3xl font-bold gradient-text font-display mb-2">Linas AI</h1>
        <p className="text-slate-600 text-base mb-6">Loading dashboard…</p>

        <div className="w-56 h-1.5 bg-white/40 rounded-full mx-auto overflow-hidden">
          <div className="h-full w-1/2 bg-gradient-to-r from-primary-500 to-secondary-500 rounded-full animate-pulse" />
        </div>
      </div>
    </div>
  );
};

export default LoadingScreen;
