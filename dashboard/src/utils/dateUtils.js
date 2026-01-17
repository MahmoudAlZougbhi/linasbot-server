/**
 * Date and Time Utility Functions
 * Handles timezone conversion and formatting for the dashboard
 */

// Default timezone from environment or fallback to Asia/Beirut (Lebanon)
const TIMEZONE = process.env.REACT_APP_TIMEZONE || 'Asia/Beirut';

/**
 * Format timestamp to localized date and time
 * @param {string|Date} timestamp - ISO timestamp or Date object
 * @param {object} options - Formatting options
 * @returns {string} Formatted date and time string
 */
export const formatDateTime = (timestamp, options = {}) => {
  if (!timestamp) return '';
  
  const {
    showDate = true,
    showTime = true,
    showSeconds = false,
    dateStyle = 'short', // 'short', 'medium', 'long', 'full'
    timeStyle = 'short', // 'short', 'medium', 'long'
  } = options;

  try {
    const date = new Date(timestamp);
    
    // Check if date is valid
    if (isNaN(date.getTime())) {
      return 'Invalid date';
    }

    const formatOptions = {
      timeZone: TIMEZONE,
    };

    if (showDate && showTime) {
      // Show both date and time
      formatOptions.dateStyle = dateStyle;
      formatOptions.timeStyle = timeStyle;
      
      if (showSeconds) {
        formatOptions.second = '2-digit';
      }
      
      return new Intl.DateTimeFormat('en-US', formatOptions).format(date);
    } else if (showDate) {
      // Show only date
      formatOptions.dateStyle = dateStyle;
      return new Intl.DateTimeFormat('en-US', formatOptions).format(date);
    } else if (showTime) {
      // Show only time
      formatOptions.timeStyle = timeStyle;
      
      if (showSeconds) {
        formatOptions.second = '2-digit';
      }
      
      return new Intl.DateTimeFormat('en-US', formatOptions).format(date);
    }

    return '';
  } catch (error) {
    console.error('Error formatting date:', error);
    return 'Invalid date';
  }
};

/**
 * Format timestamp for message bubbles (date + time)
 * @param {string|Date} timestamp - ISO timestamp or Date object
 * @returns {string} Formatted string like "12/10/2025, 3:45 PM"
 */
export const formatMessageTime = (timestamp) => {
  return formatDateTime(timestamp, {
    showDate: true,
    showTime: true,
    dateStyle: 'short',
    timeStyle: 'short',
    showSeconds: false,
  });
};

/**
 * Format timestamp for compact display (date + time without seconds)
 * @param {string|Date} timestamp - ISO timestamp or Date object
 * @returns {string} Formatted string like "Oct 12, 3:45 PM"
 */
export const formatCompactDateTime = (timestamp) => {
  if (!timestamp) return '';
  
  try {
    const date = new Date(timestamp);
    
    if (isNaN(date.getTime())) {
      return 'Invalid date';
    }

    const options = {
      timeZone: TIMEZONE,
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    };

    return new Intl.DateTimeFormat('en-US', options).format(date);
  } catch (error) {
    console.error('Error formatting compact date:', error);
    return 'Invalid date';
  }
};

/**
 * Format timestamp for full display with seconds
 * @param {string|Date} timestamp - ISO timestamp or Date object
 * @returns {string} Formatted string like "12/10/2025, 3:45:30 PM"
 */
export const formatFullDateTime = (timestamp) => {
  return formatDateTime(timestamp, {
    showDate: true,
    showTime: true,
    dateStyle: 'short',
    timeStyle: 'medium',
    showSeconds: true,
  });
};

/**
 * Get relative time (e.g., "2 minutes ago", "1 hour ago")
 * @param {string|Date} timestamp - ISO timestamp or Date object
 * @returns {string} Relative time string
 */
export const getRelativeTime = (timestamp) => {
  if (!timestamp) return '';
  
  try {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHour = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHour / 24);

    if (diffSec < 60) {
      return 'Just now';
    } else if (diffMin < 60) {
      return `${diffMin} minute${diffMin > 1 ? 's' : ''} ago`;
    } else if (diffHour < 24) {
      return `${diffHour} hour${diffHour > 1 ? 's' : ''} ago`;
    } else if (diffDay < 7) {
      return `${diffDay} day${diffDay > 1 ? 's' : ''} ago`;
    } else {
      return formatDateTime(timestamp, { showDate: true, showTime: false });
    }
  } catch (error) {
    console.error('Error calculating relative time:', error);
    return '';
  }
};

/**
 * Check if timestamp is today
 * @param {string|Date} timestamp - ISO timestamp or Date object
 * @returns {boolean} True if timestamp is today
 */
export const isToday = (timestamp) => {
  if (!timestamp) return false;
  
  try {
    const date = new Date(timestamp);
    const today = new Date();
    
    return (
      date.getDate() === today.getDate() &&
      date.getMonth() === today.getMonth() &&
      date.getFullYear() === today.getFullYear()
    );
  } catch (error) {
    return false;
  }
};

/**
 * Format duration in seconds to human-readable format
 * @param {number} seconds - Duration in seconds
 * @returns {string} Formatted duration like "2m 30s" or "1h 15m"
 */
export const formatDuration = (seconds) => {
  if (!seconds || seconds < 0) return '0s';
  
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  } else if (minutes > 0) {
    return `${minutes}m ${secs}s`;
  } else {
    return `${secs}s`;
  }
};

/**
 * Get current timezone name
 * @returns {string} Timezone name
 */
export const getTimezoneName = () => {
  return TIMEZONE;
};

/**
 * Convert UTC timestamp to local timezone
 * @param {string|Date} utcTimestamp - UTC timestamp
 * @returns {Date} Date object in local timezone
 */
export const utcToLocal = (utcTimestamp) => {
  if (!utcTimestamp) return null;
  
  try {
    return new Date(utcTimestamp);
  } catch (error) {
    console.error('Error converting UTC to local:', error);
    return null;
  }
};
