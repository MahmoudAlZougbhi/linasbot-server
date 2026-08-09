import { Feather, Ionicons } from '@expo/vector-icons';
import type { ComponentProps } from 'react';

type FeatherName = ComponentProps<typeof Feather>['name'];
type IonName = ComponentProps<typeof Ionicons>['name'];

export type AppIconName =
  | { set: 'feather'; name: FeatherName }
  | { set: 'ion'; name: IonName };

type Props = {
  icon: AppIconName;
  size?: number;
  color: string;
  /** Optional a11y name; omit when parent Pressable already labels the control. */
  accessibilityLabel?: string;
};

/** Thin-line product icons (Feather ≈ Lucide / SF-style). */
export function AppIcon({ icon, size = 20, color, accessibilityLabel }: Props) {
  const a11y = accessibilityLabel
    ? ({ accessibilityLabel, accessible: true } as const)
    : ({ accessible: false, importantForAccessibility: 'no' as const });

  if (icon.set === 'ion') {
    return <Ionicons name={icon.name} size={size} color={color} {...a11y} />;
  }
  return <Feather name={icon.name} size={size} color={color} {...a11y} />;
}

export function feather(name: FeatherName): AppIconName {
  return { set: 'feather', name };
}

export function ion(name: IonName): AppIconName {
  return { set: 'ion', name };
}
