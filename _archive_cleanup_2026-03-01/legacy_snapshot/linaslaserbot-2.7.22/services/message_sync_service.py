# -*- coding: utf-8 -*-
"""
Message Sync Service
Handles synchronization between backend appointments and message queue
"""

from datetime import datetime, timedelta
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


class MessageSyncService:
    """Handles synchronization between backend and message queue"""
    
    def __init__(self, queue_service):
        self.queue = queue_service
    
    async def incremental_sync(self):
        """Sync new and changed appointments"""
        logger.info("🔄 Starting incremental sync...")
        
        new_count = 0
        updated_count = 0
        unchanged_count = 0
        failed_count = 0
        
        try:
            # Query appointments from backend (next 30 days)
            appointments = await self._fetch_appointments()
            
            logger.info(f"📅 Found {len(appointments)} appointments from backend")
            
            for apt in appointments:
                try:
                    apt_id = apt.get('id')
                    if not apt_id:
                        failed_count += 1
                        continue
                    
                    new_fingerprint = self.queue.generate_fingerprint(apt)
                    
                    # Check if appointment changed
                    if self.queue.has_appointment_changed(apt_id, new_fingerprint):
                        if apt_id in self.queue.fingerprints:
                            # Appointment changed - cancel old messages
                            logger.debug(f"  📝 Appointment {apt_id} changed, updating...")
                            self.queue.cancel_messages_for_appointment(apt_id)
                            updated_count += 1
                        else:
                            # New appointment
                            logger.debug(f"  ✨ New appointment {apt_id}")
                            new_count += 1
                        
                        # Generate new messages
                        message_ids = await self._generate_messages_for_appointment(apt)
                        
                        # Update fingerprint
                        self.queue.update_fingerprint(apt_id, new_fingerprint, apt, message_ids)
                    else:
                        unchanged_count += 1
                
                except Exception as e:
                    logger.error(f"Error processing appointment: {e}")
                    failed_count += 1
            
            # Save after sync
            self.queue.save()
            
            logger.info(f"✅ Sync complete: {new_count} new, {updated_count} updated, {unchanged_count} unchanged, {failed_count} failed")
            
            return {
                'success': True,
                'new': new_count,
                'updated': updated_count,
                'unchanged': unchanged_count,
                'failed': failed_count,
                'total_messages': len(self.queue.messages)
            }
        
        except Exception as e:
            logger.error(f"❌ Error in incremental sync: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    async def detect_deletions(self):
        """Detect and handle deleted appointments"""
        logger.info("🗑️ Detecting deleted appointments...")
        
        try:
            # Get all appointment IDs from backend
            backend_apt_ids = await self._fetch_all_appointment_ids()
            
            # Get our tracked appointment IDs
            our_apt_ids = set(self.queue.fingerprints.keys())
            
            # Find deleted appointments
            deleted_apt_ids = our_apt_ids - backend_apt_ids
            
            cancelled_count = 0
            for apt_id in deleted_apt_ids:
                logger.debug(f"  🗑️ Appointment {apt_id} deleted, cancelling messages...")
                count = self.queue.cancel_messages_for_appointment(apt_id)
                del self.queue.fingerprints[apt_id]
                cancelled_count += count
            
            # Save after cleanup
            self.queue.save()
            
            logger.info(f"✅ Deleted {len(deleted_apt_ids)} appointments, cancelled {cancelled_count} messages")
            
            return {
                'success': True,
                'deleted_appointments': len(deleted_apt_ids),
                'cancelled_messages': cancelled_count
            }
        
        except Exception as e:
            logger.error(f"❌ Error in deletion detection: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    async def full_resync(self):
        """Complete resync - rebuild everything"""
        logger.info("🔄 Starting full resync...")
        
        try:
            # Clear old scheduled messages (older than 7 days)
            cleaned = self.queue.cleanup_old_messages(days=7)
            logger.info(f"🧹 Cleaned up {cleaned} old messages")
            
            # Clear fingerprints
            self.queue.fingerprints = {}
            
            # Re-sync everything
            result = await self.incremental_sync()
            
            logger.info("✅ Full resync complete")
            
            return result
        
        except Exception as e:
            logger.error(f"❌ Error in full resync: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _generate_messages_for_appointment(self, appointment):
        """Generate all messages for an appointment"""
        message_ids = []
        
        try:
            apt_id = appointment.get('id')
            
            # Parse appointment datetime
            apt_datetime_str = appointment.get('datetime')
            if not apt_datetime_str:
                # Try to get from appointment_details
                apt_details = appointment.get('appointment_details', {})
                apt_datetime_str = apt_details.get('date')
            
            if not apt_datetime_str:
                logger.error(f"No datetime for appointment {apt_id}")
                return message_ids
            
            # Parse datetime
            apt_datetime = self._parse_appointment_date(apt_datetime_str)
            if not apt_datetime:
                logger.error(f"Could not parse datetime: {apt_datetime_str}")
                return message_ids
            
            customer_phone = appointment.get('phone')
            customer_name = appointment.get('name', 'عميلنا العزيز')
            
            if not customer_phone:
                logger.error(f"No phone for appointment {apt_id}")
                return message_ids
            
            # Get appointment details
            apt_details = appointment.get('appointment_details', {})
            branch_name = apt_details.get('branch', appointment.get('branch', 'الفرع الرئيسي'))
            service_name = apt_details.get('service', appointment.get('service', 'جلسة ليزر'))
            
            # Generate message parameters
            parameters = {
                'customer_name': customer_name,
                'appointment_date': apt_datetime.strftime('%Y-%m-%d'),
                'appointment_time': apt_datetime.strftime('%H:%M'),
                'branch_name': branch_name,
                'service_name': service_name,
                'phone_number': '+961 1 234 567',
                'next_appointment_date': (apt_datetime + timedelta(days=17)).strftime('%Y-%m-%d')
            }
            
            current_time = datetime.now()
            
            # 1. 24h Reminder
            if apt_datetime > current_time + timedelta(hours=24):
                send_at = apt_datetime - timedelta(hours=24)
                msg_id = f"msg_{apt_id}_reminder_24h"
                
                self.queue.add_message({
                    'message_id': msg_id,
                    'appointment_id': apt_id,
                    'appointment_fingerprint': self.queue.generate_fingerprint(appointment),
                    'customer_phone': customer_phone,
                    'customer_name': customer_name,
                    'message_type': 'reminder_24h',
                    'template_id': 'reminder_24h',
                    'language': 'ar',
                    'parameters': parameters,
                    'send_at': send_at.isoformat(),
                    'status': 'scheduled',
                    'created_at': current_time.isoformat(),
                    'updated_at': current_time.isoformat(),
                    'sent_at': None,
                    'error': None,
                    'retry_count': 0,
                    'appointment_datetime': apt_datetime.isoformat(),
                    'appointment_status': appointment.get('status', 'Available')
                })
                
                message_ids.append(msg_id)
            
            # 2. Same-Day Check-in
            tomorrow = (current_time + timedelta(days=1)).date()
            if apt_datetime.date() == tomorrow:
                send_at = current_time.replace(hour=9, minute=0, second=0, microsecond=0)
                if send_at < current_time:
                    send_at += timedelta(days=1)
                
                msg_id = f"msg_{apt_id}_same_day_checkin"
                
                self.queue.add_message({
                    'message_id': msg_id,
                    'appointment_id': apt_id,
                    'appointment_fingerprint': self.queue.generate_fingerprint(appointment),
                    'customer_phone': customer_phone,
                    'customer_name': customer_name,
                    'message_type': 'same_day_checkin',
                    'template_id': 'same_day_checkin',
                    'language': 'ar',
                    'parameters': parameters,
                    'send_at': send_at.isoformat(),
                    'status': 'scheduled',
                    'created_at': current_time.isoformat(),
                    'updated_at': current_time.isoformat(),
                    'sent_at': None,
                    'error': None,
                    'retry_count': 0,
                    'appointment_datetime': apt_datetime.isoformat(),
                    'appointment_status': appointment.get('status', 'Available')
                })
                
                message_ids.append(msg_id)
            
            # 3. Post-Session Feedback (2 hours after)
            send_at = apt_datetime + timedelta(hours=2)
            if send_at > current_time:  # Only if in future
                msg_id = f"msg_{apt_id}_post_session_feedback"
                
                self.queue.add_message({
                    'message_id': msg_id,
                    'appointment_id': apt_id,
                    'appointment_fingerprint': self.queue.generate_fingerprint(appointment),
                    'customer_phone': customer_phone,
                    'customer_name': customer_name,
                    'message_type': 'post_session_feedback',
                    'template_id': 'post_session_feedback',
                    'language': 'ar',
                    'parameters': parameters,
                    'send_at': send_at.isoformat(),
                    'status': 'scheduled',
                    'created_at': current_time.isoformat(),
                    'updated_at': current_time.isoformat(),
                    'sent_at': None,
                    'error': None,
                    'retry_count': 0,
                    'appointment_datetime': apt_datetime.isoformat(),
                    'appointment_status': appointment.get('status', 'Available')
                })
                
                message_ids.append(msg_id)
            
            # 4. One-Month Follow-up (17 days after)
            send_at = apt_datetime + timedelta(days=17)
            msg_id = f"msg_{apt_id}_one_month_followup"

            self.queue.add_message({
                'message_id': msg_id,
                'appointment_id': apt_id,
                'appointment_fingerprint': self.queue.generate_fingerprint(appointment),
                'customer_phone': customer_phone,
                'customer_name': customer_name,
                'message_type': 'one_month_followup',
                'template_id': 'one_month_followup',
                'language': 'ar',
                'parameters': parameters,
                'send_at': send_at.isoformat(),
                'status': 'scheduled',
                'created_at': current_time.isoformat(),
                'updated_at': current_time.isoformat(),
                'sent_at': None,
                'error': None,
                'retry_count': 0,
                'appointment_datetime': apt_datetime.isoformat(),
                'appointment_status': appointment.get('status', 'Available')
            })

            message_ids.append(msg_id)

            # 5. Attended Yesterday / Thank You (24 hours after appointment)
            send_at = apt_datetime + timedelta(hours=24)
            if send_at > current_time:  # Only if in future
                msg_id = f"msg_{apt_id}_attended_yesterday"

                self.queue.add_message({
                    'message_id': msg_id,
                    'appointment_id': apt_id,
                    'appointment_fingerprint': self.queue.generate_fingerprint(appointment),
                    'customer_phone': customer_phone,
                    'customer_name': customer_name,
                    'message_type': 'attended_yesterday',
                    'template_id': 'attended_yesterday',
                    'language': 'ar',
                    'parameters': parameters,
                    'send_at': send_at.isoformat(),
                    'status': 'scheduled',
                    'created_at': current_time.isoformat(),
                    'updated_at': current_time.isoformat(),
                    'sent_at': None,
                    'error': None,
                    'retry_count': 0,
                    'appointment_datetime': apt_datetime.isoformat(),
                    'appointment_status': appointment.get('status', 'Available')
                })

                message_ids.append(msg_id)

            logger.debug(f"Generated {len(message_ids)} messages for appointment {apt_id}")
        
        except Exception as e:
            logger.error(f"Error generating messages for appointment: {e}", exc_info=True)
        
        return message_ids
    
    def _parse_appointment_date(self, date_str):
        """Parse appointment date from backend format"""
        if not date_str:
            return None
        
        try:
            # Format from backend: "27/10/2025 05:00:00 PM"
            return datetime.strptime(date_str, '%d/%m/%Y %I:%M:%S %p')
        except ValueError:
            # Try other formats
            for fmt in ['%d/%m/%Y %H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%d/%m/%Y', '%Y-%m-%d']:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
        return None
    
    async def _fetch_appointments(self):
        """Fetch appointments from backend"""
        from services.api_integrations import send_appointment_reminders
        
        all_appointments = []
        today = datetime.now()
        
        for days_ahead in range(30):
            query_date = (today + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
            
            try:
                result = await send_appointment_reminders(date=query_date)
                
                if result.get('success'):
                    response_data = result.get('data', {})
                    if isinstance(response_data, dict):
                        appointments = response_data.get('appointments', [])
                    elif isinstance(response_data, list):
                        appointments = response_data
                    else:
                        appointments = []
                    
                    # Add datetime to each appointment if not present
                    for apt in appointments:
                        if 'datetime' not in apt:
                            apt_details = apt.get('appointment_details', {})
                            apt['datetime'] = apt_details.get('date', '')
                    
                    all_appointments.extend(appointments)
            
            except Exception as e:
                logger.error(f"Error fetching appointments for {query_date}: {e}")
        
        return all_appointments
    
    async def _fetch_all_appointment_ids(self):
        """Fetch all appointment IDs from backend"""
        appointments = await self._fetch_appointments()
        return set(apt.get('id') for apt in appointments if apt.get('id'))


# Global instance will be created in main.py
message_sync = None
