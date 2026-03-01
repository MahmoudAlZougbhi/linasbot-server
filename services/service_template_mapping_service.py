#!/usr/bin/env python3
"""
Service Template Mapping Service - Manage which templates apply to which services
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional

from services.smart_messaging_catalog import (
    DAILY_TEMPLATE_IDS,
    CAMPAIGN_TEMPLATE_IDS,
    DEPRECATED_TEMPLATE_IDS,
    TEMPLATE_METADATA,
    normalize_template_id,
)

_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
_DATA_DIR = os.path.join(_BASE_DIR, 'data')


class ServiceTemplateMappingService:
    """
    Service to manage which message templates apply to which clinic services
    """

    def __init__(self):
        self.mapping_file = os.path.join(_DATA_DIR, 'service_template_mapping.json')
        self.templates_file = os.path.join(_DATA_DIR, 'message_templates.json')
        self.mappings = self._load_mappings()
        print(f"ServiceTemplateMappingService initialized with {len(self.mappings.get('service_mappings', {}))} services")

    def _load_mappings(self) -> Dict:
        """Load service-template mappings from JSON file"""
        if not os.path.exists(self.mapping_file):
            # Create default mappings if file doesn't exist
            return self._create_default_mappings()

        try:
            with open(self.mapping_file, 'r', encoding='utf-8') as f:
                mappings = json.load(f)
            migrated, changed = self._migrate_mappings(mappings)
            if changed:
                self._save_mappings(migrated)
            return migrated
        except Exception as e:
            print(f"Error loading service-template mappings: {e}")
            return self._create_default_mappings()

    def _migrate_mappings(self, mappings: Dict) -> tuple[Dict, bool]:
        """
        Migrate legacy template IDs and remove deprecated defaults.
        """
        changed = False
        if not isinstance(mappings, dict):
            return self._create_default_mappings(), True

        default_mapping = mappings.get("default_mapping", {})
        if not isinstance(default_mapping, dict):
            default_mapping = {}

        normalized_default = {}
        for template_id, enabled in default_mapping.items():
            canonical = normalize_template_id(template_id)
            if canonical in DEPRECATED_TEMPLATE_IDS:
                changed = True
                continue
            normalized_default[canonical] = bool(enabled)
            if canonical != template_id:
                changed = True

        for template_id in (*DAILY_TEMPLATE_IDS, *CAMPAIGN_TEMPLATE_IDS):
            if template_id not in normalized_default:
                normalized_default[template_id] = True
                changed = True

        mappings["default_mapping"] = normalized_default

        service_mappings = mappings.get("service_mappings", {})
        if not isinstance(service_mappings, dict):
            service_mappings = {}
            mappings["service_mappings"] = service_mappings
            changed = True

        for service_key, service_data in service_mappings.items():
            templates = service_data.get("templates", {})
            if not isinstance(templates, dict):
                templates = {}
                changed = True

            normalized_templates = {}
            for template_id, enabled in templates.items():
                canonical = normalize_template_id(template_id)
                if canonical in DEPRECATED_TEMPLATE_IDS:
                    changed = True
                    continue
                normalized_templates[canonical] = bool(enabled)
                if canonical != template_id:
                    changed = True

            for template_id, default_enabled in normalized_default.items():
                if template_id not in normalized_templates:
                    normalized_templates[template_id] = default_enabled
                    changed = True

            service_data["templates"] = normalized_templates
            service_mappings[service_key] = service_data

        mappings["last_updated"] = mappings.get("last_updated", datetime.now().isoformat())
        return mappings, changed

    def _create_default_mappings(self) -> Dict:
        """Create default mappings with all templates enabled for all services"""
        default_templates = {
            template_id: True
            for template_id in (*DAILY_TEMPLATE_IDS, *CAMPAIGN_TEMPLATE_IDS)
        }

        services = [
            {"service_id": 1, "service_name": "Laser Hair Removal Men"},
            {"service_id": 2, "service_name": "CO2 Laser"},
            {"service_id": 3, "service_name": "Laser Hair Removal Women"},
            {"service_id": 4, "service_name": "Laser Tattoo Removal"},
            {"service_id": 5, "service_name": "Whitinig"}
        ]

        mappings = {
            "version": "1.0",
            "last_updated": datetime.now().isoformat(),
            "default_mapping": default_templates.copy(),
            "service_mappings": {}
        }

        for service in services:
            mappings["service_mappings"][str(service["service_id"])] = {
                "service_id": service["service_id"],
                "service_name": service["service_name"],
                "templates": default_templates.copy()
            }

        self._save_mappings(mappings)
        return mappings

    def _save_mappings(self, mappings: Dict = None) -> bool:
        """Save mappings to JSON file"""
        if mappings is None:
            mappings = self.mappings

        try:
            mappings['last_updated'] = datetime.now().isoformat()
            os.makedirs(os.path.dirname(self.mapping_file), exist_ok=True)
            with open(self.mapping_file, 'w', encoding='utf-8') as f:
                json.dump(mappings, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Error saving service-template mappings: {e}")
            return False

    def get_all_mappings(self) -> Dict:
        """Get all service-template mappings"""
        # Reload to get latest
        self.mappings = self._load_mappings()
        return {
            'success': True,
            'mappings': self.mappings.get('service_mappings', {}),
            'default_mapping': self.mappings.get('default_mapping', {}),
            'last_updated': self.mappings.get('last_updated')
        }

    def get_mapping_for_service(self, service_id: int) -> Dict:
        """
        Get template mapping for a specific service

        Args:
            service_id: The service ID

        Returns:
            Dict with service info and template mappings
        """
        service_mappings = self.mappings.get('service_mappings', {})
        service_key = str(service_id)

        if service_key in service_mappings:
            return {
                'success': True,
                'service_id': service_id,
                'mapping': service_mappings[service_key]
            }

        # Return default mapping if service not found
        return {
            'success': True,
            'service_id': service_id,
            'mapping': {
                'service_id': service_id,
                'service_name': f'Service {service_id}',
                'templates': self.mappings.get('default_mapping', {})
            },
            'is_default': True
        }

    def update_mapping(self, service_id: int, templates: Dict[str, bool], service_name: str = None) -> Dict:
        """
        Update which templates a service uses

        Args:
            service_id: The service ID
            templates: Dict mapping template_id to enabled (bool)
            service_name: Optional service name to update

        Returns:
            Dict with success status
        """
        service_key = str(service_id)

        if 'service_mappings' not in self.mappings:
            self.mappings['service_mappings'] = {}

        if service_key not in self.mappings['service_mappings']:
            self.mappings['service_mappings'][service_key] = {
                'service_id': service_id,
                'service_name': service_name or f'Service {service_id}',
                'templates': {}
            }

        # Normalize template IDs and drop deprecated entries
        normalized_templates = {}
        for template_id, enabled in (templates or {}).items():
            canonical = normalize_template_id(template_id)
            if canonical in DEPRECATED_TEMPLATE_IDS:
                continue
            normalized_templates[canonical] = bool(enabled)

        for template_id, default_enabled in self.mappings.get('default_mapping', {}).items():
            normalized_templates.setdefault(template_id, bool(default_enabled))

        # Update templates
        self.mappings['service_mappings'][service_key]['templates'] = normalized_templates

        # Update service name if provided
        if service_name:
            self.mappings['service_mappings'][service_key]['service_name'] = service_name

        if self._save_mappings():
            return {
                'success': True,
                'service_id': service_id,
                'mapping': self.mappings['service_mappings'][service_key]
            }

        return {'success': False, 'error': 'Failed to save mappings'}

    def toggle_template_for_service(self, service_id: int, template_id: str, enabled: bool) -> Dict:
        """
        Toggle a single template for a service

        Args:
            service_id: The service ID
            template_id: The template ID to toggle
            enabled: True to enable, False to disable

        Returns:
            Dict with success status
        """
        service_key = str(service_id)
        template_id = normalize_template_id(template_id)
        if template_id in DEPRECATED_TEMPLATE_IDS:
            return {'success': False, 'error': f'Template {template_id} is deprecated'}

        if service_key not in self.mappings.get('service_mappings', {}):
            # Create entry with defaults
            self.mappings['service_mappings'][service_key] = {
                'service_id': service_id,
                'service_name': f'Service {service_id}',
                'templates': self.mappings.get('default_mapping', {}).copy()
            }

        self.mappings['service_mappings'][service_key]['templates'][template_id] = enabled

        if self._save_mappings():
            return {
                'success': True,
                'service_id': service_id,
                'template_id': template_id,
                'enabled': enabled
            }

        return {'success': False, 'error': 'Failed to save mapping'}

    def is_template_enabled_for_service(self, service_id: int, template_id: str) -> bool:
        """
        Check if a template is enabled for a service

        Args:
            service_id: The service ID
            template_id: The template ID

        Returns:
            True if template is enabled for the service
        """
        service_key = str(service_id)
        template_id = normalize_template_id(template_id)
        service_mappings = self.mappings.get('service_mappings', {})

        if service_key in service_mappings:
            templates = service_mappings[service_key].get('templates', {})
            return templates.get(template_id, True)  # Default to True if not specified

        # Use default mapping
        default_mapping = self.mappings.get('default_mapping', {})
        return default_mapping.get(template_id, True)

    def get_available_services(self) -> List[Dict]:
        """Get list of all available services"""
        services = []
        for service_id, service_data in self.mappings.get('service_mappings', {}).items():
            services.append({
                'service_id': service_data.get('service_id', int(service_id)),
                'service_name': service_data.get('service_name', f'Service {service_id}')
            })

        # Sort by service_id
        services.sort(key=lambda x: x['service_id'])
        return services

    def get_available_templates(self) -> List[Dict]:
        """Get list of all available template types (including custom templates)"""
        templates = []
        for template_id in (*DAILY_TEMPLATE_IDS, *CAMPAIGN_TEMPLATE_IDS):
            meta = TEMPLATE_METADATA.get(template_id, {})
            templates.append({
                "id": template_id,
                "name": meta.get("name", template_id),
                "isDefault": True,
            })

        # Add custom templates from message_templates.json
        try:
            template_file = self.templates_file
            if os.path.exists(template_file):
                with open(template_file, 'r', encoding='utf-8') as f:
                    all_templates = json.load(f)

                default_ids = {t['id'] for t in templates}
                for template_id, template_data in all_templates.items():
                    canonical_id = normalize_template_id(template_id)
                    if canonical_id in DEPRECATED_TEMPLATE_IDS:
                        continue
                    if canonical_id not in default_ids:
                        templates.append({
                            'id': canonical_id,
                            'name': template_data.get('name', template_id),
                            'isDefault': False,
                            'isCustom': True
                        })
                        default_ids.add(canonical_id)
        except Exception as e:
            print(f"Error loading custom templates: {e}")

        return templates

    def reset_service_to_defaults(self, service_id: int) -> Dict:
        """Reset a service to use default template mappings"""
        service_key = str(service_id)

        if service_key in self.mappings.get('service_mappings', {}):
            self.mappings['service_mappings'][service_key]['templates'] = \
                self.mappings.get('default_mapping', {}).copy()

            if self._save_mappings():
                return {
                    'success': True,
                    'service_id': service_id,
                    'mapping': self.mappings['service_mappings'][service_key]
                }

        return {'success': False, 'error': f'Service {service_id} not found'}

    def reset_all_to_defaults(self) -> Dict:
        """Reset all services to use default template mappings"""
        default_templates = self.mappings.get('default_mapping', {})

        for service_key in self.mappings.get('service_mappings', {}):
            self.mappings['service_mappings'][service_key]['templates'] = default_templates.copy()

        if self._save_mappings():
            return {
                'success': True,
                'message': 'All services reset to default template mappings'
            }

        return {'success': False, 'error': 'Failed to save mappings'}


# Singleton instance
service_template_mapping_service = ServiceTemplateMappingService()
