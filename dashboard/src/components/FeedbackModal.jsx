import React, { useState } from 'react';
import { motion } from 'framer-motion';
import toast from 'react-hot-toast';

const FeedbackModal = ({ message, conversation, onClose, onSubmit }) => {
  const [correctAnswer, setCorrectAnswer] = useState("");
  const [feedbackReason, setFeedbackReason] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!correctAnswer.trim()) {
      toast.error("Please provide the correct answer");
      return;
    }

    setIsSubmitting(true);
    try {
      await onSubmit(correctAnswer, feedbackReason);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        className="bg-white rounded-2xl p-6 max-w-md w-full mx-4 shadow-2xl"
      >
        <h3 className="text-lg font-bold text-slate-800 mb-4 flex items-center">
          <span className="text-2xl mr-2">✏️</span>
          Correct the Bot's Answer
        </h3>
        
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              Bot's Answer (Wrong):
            </label>
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-slate-700 max-h-32 overflow-y-auto">
              {message.content}
            </div>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              Correct Answer: <span className="text-red-500">*</span>
            </label>
            <textarea
              value={correctAnswer}
              onChange={(e) => setCorrectAnswer(e.target.value)}
              placeholder="Enter the correct answer that the bot should have given..."
              className="input-field w-full h-24 resize-none"
              disabled={isSubmitting}
              autoFocus
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              Reason (Optional):
            </label>
            <select
              value={feedbackReason}
              onChange={(e) => setFeedbackReason(e.target.value)}
              className="input-field w-full"
              disabled={isSubmitting}
            >
              <option value="">Select reason...</option>
              <option value="incorrect_info">Incorrect Information</option>
              <option value="wrong_language">Wrong Language</option>
              <option value="inappropriate_tone">Inappropriate Tone</option>
              <option value="didnt_understand">Didn't Understand Question</option>
              <option value="outdated_info">Outdated Information</option>
              <option value="missing_info">Missing Information</option>
              <option value="other">Other</option>
            </select>
          </div>
          
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-xs text-blue-700">
            <strong>💡 Tip:</strong> The bot will learn from this correction and use it for similar questions in the future.
          </div>
          
          <div className="flex space-x-3">
            <button
              onClick={handleSubmit}
              disabled={isSubmitting || !correctAnswer.trim()}
              className="btn-primary flex-1 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSubmitting ? (
                <>
                  <span className="animate-spin mr-2">⏳</span>
                  Training Bot...
                </>
              ) : (
                <>
                  <span className="mr-2">✓</span>
                  Train Bot
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

export default FeedbackModal;
