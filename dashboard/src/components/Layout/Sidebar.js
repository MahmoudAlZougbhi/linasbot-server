import React, { useMemo } from "react";
import { NavLink } from "react-router-dom";
import { motion } from "framer-motion";
import {
  HomeIcon,
  BeakerIcon,
  AcademicCapIcon,
  FolderIcon,
  ChatBubbleLeftRightIcon,
  ClockIcon,
  ChartBarIcon,
  BellIcon,
  Cog6ToothIcon,
  XMarkIcon,
  SparklesIcon,
} from "@heroicons/react/24/outline";
import { useAuth } from "../../contexts/AuthContext";
import { hasPermission } from "../../utils/permissions";
import { buildDisplayLabel } from "../../utils/buildInfo";

// Navigation items with permission keys
const navigationItems = [
  { name: "Dashboard", href: "/", icon: HomeIcon, permissionKey: "dashboard" },
  {
    name: "Testing Lab",
    href: "/testing",
    icon: BeakerIcon,
    badge: "Active",
    permissionKey: "testing",
  },
  {
    name: "AI Training",
    href: "/training",
    icon: AcademicCapIcon,
    badge: "Active",
    permissionKey: "training",
  },
  {
    name: "Content Managers",
    href: "/content-managers",
    icon: FolderIcon,
    badge: "New",
    permissionKey: "training",
  },
  {
    name: "Live Chat",
    href: "/live-chat",
    icon: ChatBubbleLeftRightIcon,
    badge: "Active",
    permissionKey: "liveChat",
  },
  {
    name: "Chat History",
    href: "/chat-history",
    icon: ClockIcon,
    badge: "Active",
    permissionKey: "chatHistory",
  },
  {
    name: "Analytics",
    href: "/analytics",
    icon: ChartBarIcon,
    badge: "Active",
    permissionKey: "analytics",
  },
  {
    name: "Smart Messaging",
    href: "/smart-messaging",
    icon: BellIcon,
    badge: "Active",
    permissionKey: "smartMessaging",
  },
  { name: "Settings", href: "/settings", icon: Cog6ToothIcon, permissionKey: "settings" },
];

const Sidebar = ({ onClose }) => {
  const { user } = useAuth();

  // Filter navigation items based on user permissions
  const navigation = useMemo(() => {
    if (!user) return [];

    // Admin has access to everything
    if (user.role === 'admin') {
      return navigationItems;
    }

    // Filter based on permissions
    return navigationItems.filter(item => {
      if (!item.permissionKey) return true;
      return hasPermission(user, item.permissionKey);
    });
  }, [user]);

  return (
    <div className="flex flex-col w-80 h-full">
      {/* Sidebar Background */}
      <div className="glass rounded-r-3xl shadow-2xl h-full relative overflow-hidden">
        {/* Gradient Overlay */}
        <div className="absolute inset-0 bg-gradient-to-b from-primary-500/10 via-transparent to-secondary-500/10 pointer-events-none"></div>

        {/* Header */}
        <div className="relative p-6 border-b border-white/20">
          <div className="flex items-center justify-between">
            <motion.div
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ duration: 0.5 }}
              className="flex items-center space-x-3"
            >
              <div className="relative">
                <div className="w-10 h-10 bg-gradient-to-br from-primary-500 to-secondary-500 rounded-xl flex items-center justify-center shadow-lg">
                  <SparklesIcon className="w-6 h-6 text-white" />
                </div>
                <div className="absolute -top-1 -right-1 w-4 h-4 bg-green-400 rounded-full border-2 border-white animate-pulse"></div>
              </div>
              <div>
                <h1 className="text-xl font-bold gradient-text font-display">
                  Lina's AI
                </h1>
                <p className="text-sm text-slate-500">Laser Center Bot</p>
              </div>
            </motion.div>

            <button
              onClick={onClose}
              className="lg:hidden p-2 rounded-lg hover:bg-white/20 transition-colors"
            >
              <XMarkIcon className="w-5 h-5 text-slate-600" />
            </button>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-6 space-y-2">
          {navigation.map((item, index) => {
            return (
              <motion.div
                key={item.name}
                initial={{ x: -50, opacity: 0 }}
                animate={{ x: 0, opacity: 1 }}
                transition={{ duration: 0.3, delay: index * 0.1 }}
              >
                <NavLink
                  to={item.href}
                  className={({ isActive }) =>
                    `group flex items-center px-4 py-3 text-sm font-medium rounded-xl transition-all duration-200 relative overflow-hidden ${
                      isActive
                        ? "bg-gradient-to-r from-primary-500 to-secondary-500 text-white shadow-lg"
                        : "text-slate-700 hover:bg-white/50 hover:text-slate-900"
                    }`
                  }
                >
                  {({ isActive }) => (
                    <>
                      {isActive && (
                        <motion.div
                          layoutId="activeTab"
                          className="absolute inset-0 bg-gradient-to-r from-primary-500 to-secondary-500 rounded-xl"
                          transition={{
                            type: "spring",
                            bounce: 0.2,
                            duration: 0.6,
                          }}
                        />
                      )}
                      <div className="relative flex items-center w-full">
                        <item.icon
                          className={`mr-3 h-5 w-5 transition-colors ${
                            isActive
                              ? "text-white"
                              : "text-slate-500 group-hover:text-slate-700"
                          }`}
                        />
                        <span className="flex-1">{item.name}</span>
                        {item.badge && (
                          <span
                            className={`ml-2 px-2 py-1 text-xs font-medium rounded-full ${
                              item.badge === "Active"
                                ? "bg-green-100 text-green-700"
                                : "bg-amber-100 text-amber-700"
                            }`}
                          >
                            {item.badge}
                          </span>
                        )}
                      </div>
                    </>
                  )}
                </NavLink>
              </motion.div>
            );
          })}
        </nav>

        {/* Footer */}
        <div className="p-6 border-t border-white/20">
          <motion.div
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ duration: 0.5, delay: 0.8 }}
            className="glass rounded-xl p-4 bg-gradient-to-r from-primary-50 to-secondary-50"
          >
            <div className="flex items-center space-x-3">
              <div className="w-8 h-8 bg-gradient-to-br from-green-400 to-emerald-500 rounded-lg flex items-center justify-center">
                <div className="w-3 h-3 bg-white rounded-full animate-pulse"></div>
              </div>
              <div>
                <p className="text-sm font-medium text-slate-700">
                  System Status
                </p>
                <p className="text-xs text-green-600 font-medium">
                  All Systems Online
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  Build {buildDisplayLabel}
                </p>
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  );
};

export default Sidebar;
