import { useEffect, useMemo, useState } from "react";
import { NavLink } from "react-router-dom";
import { motion } from "framer-motion";
import {
  HomeIcon,
  BeakerIcon,
  AcademicCapIcon,
  FolderIcon,
  ChatBubbleLeftRightIcon,
  ArrowDownTrayIcon,
  ArrowPathRoundedSquareIcon,
  BellIcon,
  Cog6ToothIcon,
  XMarkIcon,
  SparklesIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
} from "@heroicons/react/24/outline";
import { useAuth } from "../../contexts/AuthContext";
import { hasPermission } from "../../utils/permissions";
import { buildDisplayLabel } from "../../utils/buildInfo";
import { authFetch } from "../../utils/authFetch";

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
    name: "FAQ / Bot Training",
    href: "/content-managers/faq",
    icon: AcademicCapIcon,
    badge: "CM",
    permissionKey: "contentManagers",
  },
  {
    name: "Legacy FAQ",
    href: "/training",
    icon: AcademicCapIcon,
    permissionKey: "training",
    hideWhenFaqCanonical: true,
  },
  {
    name: "Content Managers",
    href: "/content-managers",
    icon: FolderIcon,
    badge: "New",
    permissionKey: "contentManagers",
  },
  {
    name: "Interaction Logs",
    href: "/activity-flow",
    icon: ArrowPathRoundedSquareIcon,
    badge: "New",
    permissionKey: "activityFlow",
  },
  {
    name: "Live Chat",
    href: "/live-chat",
    icon: ChatBubbleLeftRightIcon,
    badge: "Active",
    permissionKey: "liveChat",
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

const downloadItems = [
  {
    name: "Download Live Chat APK",
    href: "/downloads/live-chat-android.apk",
    icon: ArrowDownTrayIcon,
    badge: "Android",
    permissionKey: "liveChat",
  },
];

/** @param {{ collapsed: boolean; onToggleCollapse: () => void; onClose?: () => void }} props */
const Sidebar = ({ collapsed, onToggleCollapse, onClose }) => {
  const { user } = useAuth();
  const [faqCanonical, setFaqCanonical] = useState(false);
  const [healthState, setHealthState] = useState({
    status: "unknown",
    detail: "Checking…",
  });

  useEffect(() => {
    let cancelled = false;
    const loadMeta = async () => {
      try {
        const res = await authFetch("/api/cm/meta");
        if (!res.ok || cancelled) return;
        const data = await res.json();
        if (!cancelled) {
          setFaqCanonical(Boolean(data?.faq_canonical));
        }
      } catch {
        // Keep Legacy FAQ visible if meta is unavailable.
      }
    };
    void loadMeta();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const res = await authFetch("/api/health");
        if (!res.ok) {
          if (!cancelled) {
            setHealthState({ status: "down", detail: `HTTP ${res.status}` });
          }
          return;
        }
        const data = await res.json();
        if (cancelled) return;
        if (data?.ok) {
          setHealthState({ status: "ok", detail: "Ready" });
        } else {
          setHealthState({
            status: "degraded",
            detail: data?.status || data?.detail || "Not ready",
          });
        }
      } catch (e) {
        if (!cancelled) {
          setHealthState({
            status: "down",
            detail: e instanceof Error ? e.message : "Unreachable",
          });
        }
      }
    };
    check();
    const id = setInterval(check, 60000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  // Filter navigation items based on user permissions
  const navigation = useMemo(() => {
    if (!user) return [];

    /** @param {typeof navigationItems[number]} item */
    const keepItem = (item) => {
      if (item.hideWhenFaqCanonical && faqCanonical) return false;
      if (!item.permissionKey) return true;
      if (user.role === "admin") return true;
      return hasPermission(user, item.permissionKey);
    };

    return navigationItems.filter(keepItem);
  }, [user, faqCanonical]);

  const downloads = useMemo(() => {
    if (!user) return [];

    if (user.role === "admin") {
      return downloadItems;
    }

    return downloadItems.filter((item) => {
      if (!item.permissionKey) return true;
      return hasPermission(user, item.permissionKey);
    });
  }, [user]);

  return (
    <div className={`flex flex-col h-full ${collapsed ? "w-20" : "w-80"}`}>
      {/* Sidebar Background */}
      <div className="glass rounded-r-3xl shadow-2xl h-full relative overflow-hidden">
        {/* Gradient Overlay */}
        <div className="absolute inset-0 bg-gradient-to-b from-primary-500/10 via-transparent to-secondary-500/10 pointer-events-none"></div>

        {/* Header */}
        <div className={`relative border-b border-white/20 ${collapsed ? "p-3" : "p-6"}`}>
          <div className={`flex items-center ${collapsed ? "flex-col gap-2" : "justify-between"}`}>
            <motion.div
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ duration: 0.5 }}
              className={`flex items-center ${collapsed ? "flex-col" : "space-x-3"}`}
            >
              <div className="relative">
                <div className="w-10 h-10 bg-gradient-to-br from-primary-500 to-secondary-500 rounded-xl flex items-center justify-center shadow-lg">
                  <SparklesIcon className="w-6 h-6 text-white" />
                </div>
                <div className="absolute -top-1 -right-1 w-4 h-4 bg-green-400 rounded-full border-2 border-white animate-pulse"></div>
              </div>
              {!collapsed && (
                <div>
                  <h1 className="text-xl font-bold gradient-text font-display">
                    Lina{"'"}s AI
                  </h1>
                  <p className="text-sm text-slate-500">Laser Center Bot</p>
                </div>
              )}
            </motion.div>

            <div className="flex items-center gap-1">
              <button
                onClick={onToggleCollapse}
                className="p-2 rounded-lg hover:bg-white/20 transition-colors"
                title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              >
                {collapsed ? (
                  <ChevronRightIcon className="w-5 h-5 text-slate-600" />
                ) : (
                  <ChevronLeftIcon className="w-5 h-5 text-slate-600" />
                )}
              </button>
              {onClose && (
                <button
                  onClick={onClose}
                  className="lg:hidden p-2 rounded-lg hover:bg-white/20 transition-colors"
                >
                  <XMarkIcon className="w-5 h-5 text-slate-600" />
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className={`flex-1 space-y-2 ${collapsed ? "p-2" : "p-6"}`}>
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
                  title={collapsed ? item.name : undefined}
                  className={({ isActive }) =>
                    `group flex items-center rounded-xl transition-all duration-200 relative overflow-hidden ${
                      collapsed ? "px-3 py-3 justify-center" : "px-4 py-3"
                    } text-sm font-medium ${
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
                          className={`h-5 w-5 transition-colors flex-shrink-0 ${
                            collapsed ? "" : "mr-3"
                          } ${
                            isActive
                              ? "text-white"
                              : "text-slate-500 group-hover:text-slate-700"
                          }`}
                        />
                        {!collapsed && (
                          <>
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
                          </>
                        )}
                      </div>
                    </>
                  )}
                </NavLink>
              </motion.div>
            );
          })}

          {downloads.length > 0 && (
            <div className={`${collapsed ? "pt-2" : "pt-4"} border-t border-white/20`}>
              {!collapsed && (
                <p className="px-2 pb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
                  Mobile App
                </p>
              )}
              {downloads.map((item) => (
                <motion.div
                  key={item.name}
                  initial={{ x: -50, opacity: 0 }}
                  animate={{ x: 0, opacity: 1 }}
                  transition={{ duration: 0.3 }}
                >
                  <a
                    href={item.href}
                    download
                    title={collapsed ? item.name : undefined}
                    className={`group flex items-center rounded-xl transition-all duration-200 relative overflow-hidden ${
                      collapsed ? "px-3 py-3 justify-center" : "px-4 py-3"
                    } text-sm font-medium text-slate-700 hover:bg-white/50 hover:text-slate-900`}
                  >
                    <div className="relative flex items-center w-full">
                      <item.icon
                        className={`h-5 w-5 transition-colors flex-shrink-0 ${
                          collapsed ? "" : "mr-3"
                        } text-slate-500 group-hover:text-slate-700`}
                      />
                      {!collapsed && (
                        <>
                          <span className="flex-1">{item.name}</span>
                          {item.badge && (
                            <span className="ml-2 px-2 py-1 text-xs font-medium rounded-full bg-emerald-100 text-emerald-700">
                              {item.badge}
                            </span>
                          )}
                        </>
                      )}
                    </div>
                  </a>
                </motion.div>
              ))}
            </div>
          )}
        </nav>

        {/* Footer */}
        {!collapsed && (
          <div className="p-6 border-t border-white/20">
            <motion.div
              initial={{ y: 20, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ duration: 0.5, delay: 0.8 }}
              className="glass rounded-xl p-4 bg-gradient-to-r from-primary-50 to-secondary-50"
            >
              <div className="flex items-center space-x-3">
                <div
                  className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                    healthState.status === "ok"
                      ? "bg-gradient-to-br from-green-400 to-emerald-500"
                      : healthState.status === "degraded"
                        ? "bg-gradient-to-br from-amber-400 to-orange-500"
                        : "bg-gradient-to-br from-slate-400 to-slate-500"
                  }`}
                >
                  <div className="w-3 h-3 bg-white rounded-full"></div>
                </div>
                <div>
                  <p className="text-sm font-medium text-slate-700">
                    System health
                  </p>
                  <p
                    className={`text-xs font-medium ${
                      healthState.status === "ok"
                        ? "text-green-600"
                        : healthState.status === "degraded"
                          ? "text-amber-600"
                          : "text-slate-600"
                    }`}
                  >
                    {healthState.detail}
                  </p>
                  <p className="text-xs text-slate-500 mt-1">
                    Build {buildDisplayLabel}
                  </p>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Sidebar;
