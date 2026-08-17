/** First N lines stay inline; longer Note/Description fields get See all. */
export const SEE_ALL_MAX_LINES = 10;
export const SEE_ALL_LINE_HEIGHT = 22;

export function countTextLines(text: string): number {
  if (!text) return 0;
  return text.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n').length;
}

export function needsSeeAll(text: string, contentHeight?: number): boolean {
  if (countTextLines(text) > SEE_ALL_MAX_LINES) return true;
  if (contentHeight != null && contentHeight > SEE_ALL_MAX_LINES * SEE_ALL_LINE_HEIGHT + 1) {
    return true;
  }
  return false;
}

export function seeAllMaxHeight(paddingVertical = 12): number {
  return SEE_ALL_MAX_LINES * SEE_ALL_LINE_HEIGHT + paddingVertical * 2;
}
