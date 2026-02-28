# -*- coding: utf-8 -*-
"""
Message Queue Service
Persistent message queue with sync capabilities and template activation control
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class MessageQueueService:
    """Persistent message queue with sync capabilities"""
    
    def __init__(self):
        self.queue_file = 'data/message_queue.json'
        self.fingerprints_file = 'data/appointment_fingerprints.json'
        self.template_status_file = 'data/template_activation_status.json'
        
        self.messages = {}
        self.fingerprints = {}
        self.template_status = {}
        
        self.load()
    
    def _load_json(self, filepath, default=None):
        """Load JSON file with error handling"""
        if default is None:
            default = {}
        
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading {filepath}: {e}")
                return default
        return default
    
    def _save_json(self, filepath, data):
        """Save JSON file with error handling"""
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving {filepath}: {e}")
            return False
    
    def load(self):
        """Load queue, fingerprints, and template status from disk"""
        logger.info("📂 Loading message queue from disk...")
        
        # Load messages
        queue_data = self._load_json(self.queue_file, {'messages': {}, 'metadata': {}})
        self.messages = queue_data.get('messages', {})
        
        # Load fingerprints
        fingerprints_data = self._load_json(self.fingerprints_file, {'fingerprints': {}, 'metadata': {}})
        self.fingerprints = fingerprints_data.get('fingerprints', {})
        
        # Load template status
        self.template_status = self._load_json(self.template_status_file, {})
        
        # Initialize template status if empty (all active by default)
        if not self.template_status:
            self.template_status = {
                'reminder_24h': {'active': True, 'updated_at': datetime.now().isoformat()},
                'same_day_checkin': {'active': True, 'updated_at': datetime.now().isoformat()},
                'post_session_feedback': {'active': True, 'updated_at': datetime.now().isoformat()},
                'no_show_followup': {'active': True, 'updated_at': datetime.now().isoformat()},
                'one_month_followup': {'active': True, 'updated_at': datetime.now().isoformat()},
                'missed_yesterday': {'active': True, 'updated_at': datetime.now().isoformat()},
                'missed_this_month': {'active': True, 'updated_at': datetime.now().isoformat()},
                'attended_yesterday': {'active': True, 'updated_at': datetime.now().isoformat()}
            }
            self._save_json(self.template_status_file, self.template_status)
        
        logger.info(f"✅ Loaded {len(self.messages)} messages, {len(self.fingerprints)} fingerprints")
    
    def save(self):
        """Save queue and fingerprints to disk"""
        # Save messages with metadata
        queue_data = {
            'messages': self.messages,
            'metadata': self._get_metadata()
        }
        self._save_json(self.queue_file, queue_data)
        
        # Save fingerprints with metadata
        fingerprints_data = {
            'fingerprints': self.fingerprints,
            'metadata': {
                'total_appointments': len(self.fingerprints),
                'last_cleanup': datetime.now().isoformat()
            }
        }
        self._save_json(self.fingerprints_file, fingerprints_data)
    
    def _get_metadata(self):
        """Get queue metadata"""
        stats = self.get_statistics()
        return {
            'last_sync': datetime.now().isoformat(),
            'total_messages': stats['total'],
            'scheduled': stats['scheduled'],
            'sent': stats['sent'],
            'failed': stats['failed'],
            'cancelled': stats['cancelled'],
            'deactivated': stats['deactivated'],
            'version': '1.0'
        }
    
    def add_message(self, message_data):
        """Add message to queue with smart messaging controls"""
        message_id = message_data['message_id']

        # Check if smart messaging is globally enabled
        if not self._is_smart_messaging_enabled():
            message_data['status'] = 'disabled_globally'
            logger.debug(f"Smart messaging is disabled globally, skipping message")
            self.messages[message_id] = message_data
            return

        # Check if template is active
        template_id = message_data.get('template_id', message_data.get('message_type'))
        if not self.is_template_active(template_id):
            message_data['status'] = 'deactivated'
            logger.debug(f"Template {template_id} is inactive, marking message as deactivated")
            self.messages[message_id] = message_data
            return

        # Check service-template mapping
        service_id = message_data.get('service_id')
        if service_id and not self._is_template_enabled_for_service(service_id, template_id):
            message_data['status'] = 'skipped_service_mismatch'
            logger.debug(f"Template {template_id} not enabled for service {service_id}")
            self.messages[message_id] = message_data
            return

        # Check if preview mode is enabled
        if self._is_preview_mode_enabled():
            message_data['status'] = 'pending_approval'
            logger.debug(f"Preview mode enabled, message {message_id} pending approval")
            # Also add to preview queue service
            self._add_to_preview_queue(message_data)
        else:
            # Keep original status (usually 'scheduled')
            pass

        self.messages[message_id] = message_data
        logger.debug(f"Added message {message_id} with status {message_data['status']}")

    def _is_smart_messaging_enabled(self):
        """Check if smart messaging is globally enabled"""
        try:
            settings_file = 'data/app_settings.json'
            if os.path.exists(settings_file):
                with open(settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                return settings.get('smartMessaging', {}).get('enabled', True)
        except Exception as e:
            logger.error(f"Error checking smart messaging status: {e}")
        return True  # Default to enabled

    def _is_preview_mode_enabled(self):
        """Check if preview mode is enabled"""
        try:
            settings_file = 'data/app_settings.json'
            if os.path.exists(settings_file):
                with open(settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                return settings.get('smartMessaging', {}).get('previewBeforeSend', True)
        except Exception as e:
            logger.error(f"Error checking preview mode status: {e}")
        return True  # Default to preview mode enabled

    def _is_template_enabled_for_service(self, service_id, template_id):
        """Check if template is enabled for a specific service"""
        try:
            mapping_file = 'data/service_template_mapping.json'
            if os.path.exists(mapping_file):
                with open(mapping_file, 'r', encoding='utf-8') as f:
                    mappings = json.load(f)
                service_key = str(service_id)
                service_mapping = mappings.get('service_mappings', {}).get(service_key, {})
                templates = service_mapping.get('templates', {})
                return templates.get(template_id, True)  # Default to enabled if not specified
        except Exception as e:
            logger.error(f"Error checking service-template mapping: {e}")
        return True  # Default to enabled

    def _add_to_preview_queue(self, message_data):
        """Add message to preview queue service"""
        try:
            from services.message_preview_service import message_preview_service
            message_preview_service.add_to_preview_queue(message_data)
        except Exception as e:
            logger.error(f"Error adding to preview queue: {e}")
    
    def update_message_status(self, message_id, status, error=None):
        """Update message status"""
        if message_id in self.messages:
            self.messages[message_id]['status'] = status
            self.messages[message_id]['updated_at'] = datetime.now().isoformat()
            
            if error:
                self.messages[message_id]['error'] = error
            
            if status == 'sent':
                self.messages[message_id]['sent_at'] = datetime.now().isoformat()
            
            logger.debug(f"Updated message {message_id} status to {status}")
            return True
        return False
    
    def get_due_messages(self):
        """Get messages that should be sent now (only scheduled and active templates)"""
        current_time = datetime.now()
        due_messages = []
        
        for msg_id, msg_data in self.messages.items():
            # Only send scheduled messages
            if msg_data['status'] != 'scheduled':
                continue
            
            # Check if template is active
            template_id = msg_data.get('template_id', msg_data.get('message_type'))
            if not self.is_template_active(template_id):
                continue
            
            # Check if due
            try:
                send_time = datetime.fromisoformat(msg_data['send_at'])
                if send_time <= current_time:
                    due_messages.append(msg_data)
            except:
                logger.error(f"Invalid send_at time for message {msg_id}")
        
        return due_messages
    
    def cancel_messages_for_appointment(self, appointment_id):
        """Cancel all messages for an appointment"""
        cancelled_count = 0
        
        for msg_id, msg_data in self.messages.items():
            if msg_data.get('appointment_id') == appointment_id:
                if msg_data['status'] in ['scheduled', 'deactivated']:
                    self.update_message_status(msg_id, 'cancelled')
                    cancelled_count += 1
        
        logger.info(f"Cancelled {cancelled_count} messages for appointment {appointment_id}")
        return cancelled_count
    
    def generate_fingerprint(self, appointment):
        """Generate unique fingerprint for appointment"""
        apt_id = appointment.get('id')
        apt_datetime = appointment.get('datetime', appointment.get('date', ''))
        apt_status = appointment.get('status', 'Available')
        return f"{apt_id}_{apt_datetime}_{apt_status}"
    
    def has_appointment_changed(self, apt_id, new_fingerprint):
        """Check if appointment has changed"""
        if apt_id not in self.fingerprints:
            return True  # New appointment
        
        old_fingerprint = self.fingerprints[apt_id].get('fingerprint')
        return old_fingerprint != new_fingerprint
    
    def update_fingerprint(self, apt_id, fingerprint, appointment_data, message_ids):
        """Update appointment fingerprint"""
        self.fingerprints[apt_id] = {
            'appointment_id': apt_id,
            'fingerprint': fingerprint,
            'customer_phone': appointment_data.get('phone'),
            'appointment_datetime': appointment_data.get('datetime'),
            'appointment_status': appointment_data.get('status'),
            'last_seen': datetime.now().isoformat(),
            'messages_generated': message_ids
        }
    
    def get_statistics(self):
        """Get queue statistics"""
        stats = {
            'total': len(self.messages),
            'scheduled': 0,
            'sent': 0,
            'failed': 0,
            'cancelled': 0,
            'deactivated': 0,
            'pending_approval': 0,
            'approved': 0,
            'rejected': 0,
            'skipped_service_mismatch': 0,
            'disabled_globally': 0
        }

        for msg_data in self.messages.values():
            status = msg_data.get('status', 'scheduled')
            if status in stats:
                stats[status] += 1
            else:
                stats[status] = 1

        return stats
    
    def cleanup_old_messages(self, days=7):
        """Remove old scheduled/deactivated messages"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        to_remove = []
        for msg_id, msg_data in self.messages.items():
            if msg_data['status'] in ['scheduled', 'deactivated']:
                try:
                    send_at = datetime.fromisoformat(msg_data['send_at'])
                    if send_at < cutoff_date:
                        to_remove.append(msg_id)
                except:
                    pass
        
        for msg_id in to_remove:
            del self.messages[msg_id]
        
        logger.info(f"🧹 Cleaned up {len(to_remove)} old messages")
        return len(to_remove)
    
    # ==================== TEMPLATE ACTIVATION CONTROL ====================
    
    def is_template_active(self, template_id):
        """Check if a template is active"""
        return self.template_status.get(template_id, {}).get('active', True)
    
    def set_template_active(self, template_id, active):
        """Set template active/inactive status"""
        if template_id not in self.template_status:
            self.template_status[template_id] = {}
        
        old_status = self.template_status[template_id].get('active', True)
        self.template_status[template_id]['active'] = active
        self.template_status[template_id]['updated_at'] = datetime.now().isoformat()
        
        # Save template status
        self._save_json(self.template_status_file, self.template_status)
        
        # Update all messages with this template
        if active and not old_status:
            # Template activated: scheduled -> scheduled (reactivate)
            count = self._reactivate_template_messages(template_id)
            logger.info(f"✅ Activated template {template_id}, reactivated {count} messages")
        elif not active and old_status:
            # Template deactivated: scheduled -> deactivated
            count = self._deactivate_template_messages(template_id)
            logger.info(f"⏸️ Deactivated template {template_id}, deactivated {count} messages")
        
        self.save()
        
        return {
            'template_id': template_id,
            'active': active,
            'messages_affected': count if 'count' in locals() else 0
        }
    
    def _deactivate_template_messages(self, template_id):
        """Mark all scheduled messages of this template as deactivated"""
        count = 0
        for msg_id, msg_data in self.messages.items():
            msg_template = msg_data.get('template_id', msg_data.get('message_type'))
            if msg_template == template_id and msg_data['status'] == 'scheduled':
                self.update_message_status(msg_id, 'deactivated')
                count += 1
        return count
    
    def _reactivate_template_messages(self, template_id):
        """Mark all deactivated messages of this template as scheduled"""
        count = 0
        for msg_id, msg_data in self.messages.items():
            msg_template = msg_data.get('template_id', msg_data.get('message_type'))
            if msg_template == template_id and msg_data['status'] == 'deactivated':
                self.update_message_status(msg_id, 'scheduled')
                count += 1
        return count
    
    def get_template_status(self):
        """Get all template activation statuses"""
        return self.template_status
    
    def get_messages_by_template(self, template_id):
        """Get all messages for a specific template"""
        messages = []
        for msg_id, msg_data in self.messages.items():
            msg_template = msg_data.get('template_id', msg_data.get('message_type'))
            if msg_template == template_id:
                messages.append(msg_data)
        return messages


# Global instance
message_queue = MessageQueueService()
