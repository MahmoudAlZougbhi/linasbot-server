import { ArrowPathIcon } from "@heroicons/react/24/outline";
import { formatDate, formatFileSize } from "./TrainingFileEditor.meta";

/**
 * @param {{
 *   backups: TrainingBackupRecord[];
 *   loading: boolean;
 *   handleRestore: (filename: string) => void;
 * }} props
 */
export const TrainingFileEditorBackups = ({ backups, loading, handleRestore }) => {
  if (!backups.length) return null;

  return (
    <div className="card">
      <h3 className="text-lg font-bold text-slate-800 font-display mb-4 flex items-center">
        <ArrowPathIcon className="w-5 h-5 mr-2 text-slate-600" />
        Backup History ({backups.length})
      </h3>

      <div className="space-y-2 max-h-64 overflow-y-auto">
        {backups.map((backup) => (
          <div
            key={backup.filename}
            className="flex items-center justify-between p-3 bg-slate-50 rounded-lg hover:bg-slate-100 transition-colors"
          >
            <div className="flex-1">
              <p className="text-sm font-medium text-slate-800">{backup.filename}</p>
              <p className="text-xs text-slate-500">
                {formatDate(backup.created)} • {formatFileSize(backup.size)}
              </p>
            </div>
            <button
              onClick={() => handleRestore(backup.filename || "")}
              disabled={loading}
              className="text-sm px-3 py-1 rounded-lg bg-blue-100 text-blue-700 hover:bg-blue-200 transition-colors disabled:opacity-50"
            >
              Restore
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};
