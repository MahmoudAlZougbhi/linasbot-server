import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  BeakerIcon,
  AcademicCapIcon,
  ChatBubbleLeftRightIcon,
  ChartBarIcon,
  CpuChipIcon,
  GlobeAltIcon,
  ClockIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';
import { useApi } from '../hooks/useApi';

const Dashboard = () => {
  const { botStatus, fetchBotStatus } = useApi();
  const [stats, setStats] = useState({
    totalTests: 0,
    trainingEntries: 0,
    responseTime: 2.1,
    uptime: '99.9%',
  });

  useEffect(() => {
    fetchBotStatus();
    // Simulate loading stats
    setTimeout(() => {
      setStats({
        totalTests: 147,
        trainingEntries: 89,
        responseTime: 2.1,
        uptime: '99.9%',
      });
    }, 1000);
  }, [fetchBotStatus]);

  const quickActions = [
    {
      name: 'Test Voice',
      description: 'Upload and test voice transcription',
      icon: BeakerIcon,
      href: '/testing',
      color: 'from-blue-500 to-cyan-500',
      active: true,
    },
    {
      name: 'Train AI',
      description: 'Add new knowledge to the bot',
      icon: AcademicCapIcon,
      href: '/training',
      color: 'from-purple-500 to-pink-500',
      active: true,
    },
    {
      name: 'Live Chat',
      description: 'Monitor real-time conversations',
      icon: ChatBubbleLeftRightIcon,
      href: '/live-chat',
      color: 'from-green-500 to-emerald-500',
      active: false,
    },
    {
      name: 'Analytics',
      description: 'View performance metrics',
      icon: ChartBarIcon,
      href: '/analytics',
      color: 'from-orange-500 to-red-500',
      active: false,
    },
  ];

  const systemStatus = [
    {
      name: 'Bot Engine',
      status: 'online',
      description: 'AI processing active',
      icon: CpuChipIcon,
    },
    {
      name: 'Multi-Language',
      status: 'online',
      description: 'AR, EN, FR, Franco support',
      icon: GlobeAltIcon,
    },
    {
      name: 'Response Time',
      status: 'good',
      description: `${stats.responseTime}s average`,
      icon: ClockIcon,
    },
    {
      name: 'WhatsApp Webhook',
      status: 'testing',
      description: 'Sandbox mode active',
      icon: ChatBubbleLeftRightIcon,
    },
  ];

  const getStatusColor = (status) => {
    switch (status) {
      case 'online':
      case 'good':
        return 'text-green-600 bg-green-100';
      case 'testing':
        return 'text-amber-600 bg-amber-100';
      case 'offline':
        return 'text-red-600 bg-red-100';
      default:
        return 'text-slate-600 bg-slate-100';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'online':
      case 'good':
        return CheckCircleIcon;
      case 'testing':
        return ExclamationTriangleIcon;
      default:
        return ExclamationTriangleIcon;
    }
  };

  return (
    <div className="space-y-8">
      {/* Welcome Section */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="text-center"
      >
        <h1 className="text-4xl font-bold gradient-text font-display mb-4">
          Welcome to Lina's AI Dashboard
        </h1>
        <p className="text-xl text-slate-600 max-w-2xl mx-auto">
          Your intelligent WhatsApp bot control center. Test, train, and monitor your AI assistant.
        </p>
      </motion.div>

      {/* Stats Grid */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.2 }}
        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6"
      >
        {[
          { label: 'Total Tests', value: stats.totalTests, change: '+12%', color: 'text-blue-600' },
          { label: 'Training Entries', value: stats.trainingEntries, change: '+8%', color: 'text-purple-600' },
          { label: 'Avg Response Time', value: `${stats.responseTime}s`, change: '-5%', color: 'text-green-600' },
          { label: 'System Uptime', value: stats.uptime, change: '+0.1%', color: 'text-orange-600' },
        ].map((stat, index) => (
          <motion.div
            key={stat.label}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.5, delay: 0.3 + index * 0.1 }}
            className="card glow-on-hover"
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-600">{stat.label}</p>
                <p className={`text-2xl font-bold ${stat.color} mt-1`}>{stat.value}</p>
              </div>
              <div className={`text-sm font-medium ${stat.change.startsWith('+') ? 'text-green-600' : 'text-red-600'}`}>
                {stat.change}
              </div>
            </div>
          </motion.div>
        ))}
      </motion.div>

      {/* Quick Actions */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.4 }}
        className="space-y-6"
      >
        <h2 className="text-2xl font-bold text-slate-800 font-display">Quick Actions</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {quickActions.map((action, index) => (
            <motion.div
              key={action.name}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.5 + index * 0.1 }}
              className={`relative overflow-hidden rounded-2xl ${action.active ? 'cursor-pointer' : 'cursor-not-allowed opacity-60'}`}
            >
              <div className={`absolute inset-0 bg-gradient-to-br ${action.color} opacity-10`}></div>
              <div className="card relative">
                <div className="flex items-center space-x-4">
                  <div className={`p-3 rounded-xl bg-gradient-to-br ${action.color} shadow-lg`}>
                    <action.icon className="w-6 h-6 text-white" />
                  </div>
                  <div className="flex-1">
                    <h3 className="font-semibold text-slate-800">{action.name}</h3>
                    <p className="text-sm text-slate-600 mt-1">{action.description}</p>
                  </div>
                </div>
                {!action.active && (
                  <div className="absolute top-2 right-2">
                    <span className="px-2 py-1 text-xs font-medium bg-amber-100 text-amber-700 rounded-full">
                      Coming Soon
                    </span>
                  </div>
                )}
              </div>
            </motion.div>
          ))}
        </div>
      </motion.div>

      {/* System Status */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.6 }}
        className="space-y-6"
      >
        <h2 className="text-2xl font-bold text-slate-800 font-display">System Status</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {systemStatus.map((system, index) => {
            const StatusIcon = getStatusIcon(system.status);
            return (
              <motion.div
                key={system.name}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.5, delay: 0.7 + index * 0.1 }}
                className="card"
              >
                <div className="flex items-center space-x-4">
                  <div className="p-3 rounded-xl bg-slate-100">
                    <system.icon className="w-6 h-6 text-slate-600" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center space-x-2">
                      <h3 className="font-semibold text-slate-800">{system.name}</h3>
                      <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${getStatusColor(system.status)}`}>
                        <StatusIcon className="w-3 h-3 mr-1" />
                        {system.status}
                      </span>
                    </div>
                    <p className="text-sm text-slate-600 mt-1">{system.description}</p>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      </motion.div>

      {/* Recent Activity */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.8 }}
        className="card"
      >
        <h2 className="text-xl font-bold text-slate-800 font-display mb-6">Recent Activity</h2>
        <div className="space-y-4">
          {[
            { action: 'Voice test completed', time: '2 minutes ago', status: 'success' },
            { action: 'Training data added', time: '5 minutes ago', status: 'success' },
            { action: 'Text message processed', time: '8 minutes ago', status: 'success' },
            { action: 'System health check', time: '15 minutes ago', status: 'success' },
          ].map((activity, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3, delay: 0.9 + index * 0.1 }}
              className="flex items-center space-x-3 p-3 rounded-lg hover:bg-slate-50 transition-colors"
            >
              <div className={`w-2 h-2 rounded-full ${activity.status === 'success' ? 'bg-green-400' : 'bg-red-400'}`}></div>
              <div className="flex-1">
                <p className="text-sm font-medium text-slate-700">{activity.action}</p>
                <p className="text-xs text-slate-500">{activity.time}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </motion.div>
    </div>
  );
};

export default Dashboard;