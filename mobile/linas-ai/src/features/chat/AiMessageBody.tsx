import { StyleSheet, Text, View } from 'react-native';

import { textDirectionStyle } from '../../lib/textDirection';
import { fonts, spacing, typography, useTheme } from '../../theme';

type Block =
  | { kind: 'section'; title: string }
  | { kind: 'bullet'; text: string }
  | { kind: 'paragraph'; text: string };

type Props = {
  content: string;
};

function stripBoldMarkers(text: string): string {
  return text.replace(/\*\*(.+?)\*\*/g, '$1').trim();
}

function parseBlocks(content: string): Block[] {
  const lines = content.split('\n');
  const blocks: Block[] = [];

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;

    const sectionMatch = line.match(/^—\s*(.+)$/);
    if (sectionMatch) {
      blocks.push({ kind: 'section', title: stripBoldMarkers(sectionMatch[1]) });
      continue;
    }

    const bulletMatch = line.match(/^[•\-–]\s+(.+)$/);
    if (bulletMatch) {
      blocks.push({ kind: 'bullet', text: stripBoldMarkers(bulletMatch[1]) });
      continue;
    }

    blocks.push({ kind: 'paragraph', text: stripBoldMarkers(line) });
  }

  return blocks;
}

function RichLine({ text, bold }: { text: string; bold?: boolean }) {
  const { colors } = useTheme();
  const dirStyle = textDirectionStyle(text);
  const parts = text.split(/(\*\*.+?\*\*)/g).filter(Boolean);

  return (
    <Text style={[styles.line, { color: colors.bubbleAiText }, dirStyle]}>
      {parts.map((part, i) => {
        const boldMatch = part.match(/^\*\*(.+)\*\*$/);
        if (boldMatch) {
          return (
            <Text key={i} style={styles.bold}>
              {boldMatch[1]}
            </Text>
          );
        }
        return (
          <Text key={i} style={bold ? styles.bold : undefined}>
            {part}
          </Text>
        );
      })}
    </Text>
  );
}

/** Structured AI reply body — teal section dashes + bullet lists. */
export function AiMessageBody({ content }: Props) {
  const { colors } = useTheme();
  const dirStyle = textDirectionStyle(content);
  const blocks = parseBlocks(content);

  if (blocks.length === 0) {
    return (
      <Text style={[styles.line, { color: colors.bubbleAiText }, dirStyle]}>
        {content}
      </Text>
    );
  }

  return (
    <View>
      {blocks.map((block, index) => {
        if (block.kind === 'section') {
          return (
            <View key={`s-${index}`} style={styles.sectionRow}>
              <Text style={[styles.sectionDash, { color: colors.accent }]}>—</Text>
              <Text style={[styles.sectionTitle, { color: colors.bubbleAiText }, dirStyle]}>
                {block.title}
              </Text>
            </View>
          );
        }

        if (block.kind === 'bullet') {
          return (
            <View
              key={`b-${index}`}
              style={[
                styles.bulletRow,
                { flexDirection: dirStyle.writingDirection === 'rtl' ? 'row-reverse' : 'row' },
              ]}
            >
              <Text style={[styles.bulletDot, { color: colors.bubbleAiText }]}>•</Text>
              <RichLine text={block.text} />
            </View>
          );
        }

        return (
          <View key={`p-${index}`} style={styles.paragraph}>
            <RichLine text={block.text} />
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  line: {
    ...typography.chatAi,
  },
  bold: {
    fontFamily: fonts.bodyMedium,
    fontWeight: '700',
  },
  sectionRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
    marginTop: spacing.sm,
    marginBottom: 4,
  },
  sectionDash: {
    fontFamily: fonts.bodyMedium,
    fontSize: 18,
    lineHeight: 27,
    fontWeight: '700',
  },
  sectionTitle: {
    ...typography.chatAi,
    fontFamily: fonts.bodyMedium,
    fontWeight: '700',
    flex: 1,
  },
  bulletRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    paddingLeft: 4,
    marginBottom: 4,
  },
  bulletDot: {
    ...typography.chatAi,
    lineHeight: 27,
    width: 12,
    textAlign: 'center',
  },
  paragraph: {
    marginBottom: 4,
  },
});
