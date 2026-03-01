import React, { useState } from 'react';
import { motion } from 'framer-motion';
import toast from 'react-hot-toast';

/**
 * Modal for "Like" on AI answers: edit question + answer, save to FAQ in 4 languages.
 */
const LikeFeedbackModal = ({ message, userQuestion, onClose, onSubmit }) => {
  const [question, setQuestion] = useState(userQuestion || '');
  const [answer, setAnswer] = useState(message?.content || '');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!question.trim() || !answer.trim()) {
      toast.error('Please provide both question and answer');
      return;
    }

    setIsSubmitting(true);
    try {
      await onSubmit(question, answer);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        className="bg-white rounded-2xl p-6 max-w-lg w-full mx-4 shadow-2xl"
      >
        <h3 className="text-lg font-bold text-slate-800 mb-4 flex items-center">
          <span className="text-2xl mr-2">👍</span>
          Save to FAQ (4 Languages)
        </h3>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              User Question: <span className="text-red-500">*</span>
            </label>
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Edit the question..."
              className="input-field w-full h-20 resize-none"
              disabled={isSubmitting}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              AI Answer: <span className="text-red-500">*</span>
            </label>
            <textarea
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              placeholder="Edit the answer..."
              className="input-field w-full h-24 resize-none"
              disabled={isSubmitting}
            />
          </div>

          <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-xs text-blue-700">
            <strong>💡 Tip:</strong> This will save to FAQ in Arabic, English, French, and Franco.
          </div>

          <div className="flex space-x-3">
            <button
              onClick={handleSubmit}
              disabled={isSubmitting || !question.trim() || !answer.trim()}
              className="btn-primary flex-1 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSubmitting ? (
                <>
                  <span className="animate-spin mr-2">⏳</span>
                  Saving...
                </>
              ) : (
                <>
                  <span className="mr-2">✓</span>
                  Save
                </>
              )}
            </button>
            <button
              onClick={onClose}
              disabled={isSubmitting}
              className="btn-ghost flex-1 disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
};

export default LikeFeedbackModal;
