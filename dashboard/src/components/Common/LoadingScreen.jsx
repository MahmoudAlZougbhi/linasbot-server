import React from 'react';
import { motion } from 'framer-motion';
import { SparklesIcon } from '@heroicons/react/24/outline';

const LoadingScreen = () => {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-100 flex items-center justify-center">
      {/* Background Effects */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-primary-200 rounded-full mix-blend-multiply filter blur-xl opacity-70 animate-pulse-slow"></div>
        <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-secondary-200 rounded-full mix-blend-multiply filter blur-xl opacity-70 animate-pulse-slow animation-delay-400"></div>
        <div className="absolute top-40 left-1/2 w-80 h-80 bg-accent-200 rounded-full mix-blend-multiply filter blur-xl opacity-70 animate-pulse-slow animation-delay-800"></div>
      </div>

      <div className="relative z-10 text-center">
        {/* Logo Animation */}
        <motion.div
          initial={{ scale: 0.5, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.8, ease: 'easeOut' }}
          className="mb-8"
        >
          <div className="relative mx-auto w-24 h-24 mb-6">
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 3, repeat: Infinity, ease: 'linear' }}
              className="absolute inset-0 bg-gradient-to-r from-primary-500 via-secondary-500 to-accent-500 rounded-full p-1"
            >
              <div className="w-full h-full bg-white rounded-full flex items-center justify-center">
                <SparklesIcon className="w-10 h-10 text-primary-600" />
              </div>
            </motion.div>
          </div>
          
          <motion.h1
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ duration: 0.6, delay: 0.3 }}
            className="text-4xl font-bold gradient-text font-display mb-2"
          >
            Lina's AI Dashboard
          </motion.h1>
          
          <motion.p
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ duration: 0.6, delay: 0.5 }}
            className="text-slate-600 text-lg"
          >
            Initializing AI Control Center
          </motion.p>
        </motion.div>

        {/* Loading Animation */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.7 }}
          className="space-y-4"
        >
          {/* Progress Bar */}
          <div className="w-64 h-2 bg-white/30 rounded-full mx-auto overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: '100%' }}
              transition={{ duration: 2, ease: 'easeInOut' }}
              className="h-full bg-gradient-to-r from-primary-500 to-secondary-500 rounded-full"
            />
          </div>

          {/* Loading Dots */}
          <div className="flex items-center justify-center space-x-2">
            {[0, 1, 2].map((index) => (
              <motion.div
                key={index}
                animate={{
                  scale: [1, 1.2, 1],
                  opacity: [0.5, 1, 0.5],
                }}
                transition={{
                  duration: 1.5,
                  repeat: Infinity,
                  delay: index * 0.2,
                }}
                className="w-3 h-3 bg-primary-500 rounded-full"
              />
            ))}
          </div>

          {/* Loading Text */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.6, delay: 1 }}
            className="text-slate-500"
          >
            <span className="loading-dots">Loading AI modules</span>
          </motion.div>
        </motion.div>

        {/* Feature Cards */}
        <motion.div
          initial={{ y: 40, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ duration: 0.8, delay: 1.2 }}
          className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-4 max-w-2xl mx-auto"
        >
          {[
            { icon: '🤖', title: 'AI Testing', desc: 'Voice & Text Analysis' },
            { icon: '🎓', title: 'Smart Training', desc: 'Knowledge Management' },
            { icon: '📊', title: 'Real-time Stats', desc: 'Performance Monitoring' },
          ].map((feature, index) => (
            <motion.div
              key={index}
              initial={{ y: 20, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ duration: 0.5, delay: 1.4 + index * 0.1 }}
              className="glass rounded-xl p-4 text-center"
            >
              <div className="text-2xl mb-2">{feature.icon}</div>
              <h3 className="font-semibold text-slate-700 text-sm">{feature.title}</h3>
              <p className="text-xs text-slate-500 mt-1">{feature.desc}</p>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </div>
  );
};

export default LoadingScreen;