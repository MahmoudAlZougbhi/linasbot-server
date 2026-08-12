import { useLiveChatActions } from "./useLiveChatActions";
import { useLiveChatData } from "./useLiveChatData";
import { useLiveChatEffects } from "./useLiveChatEffects";
import { useLiveChatFeedback } from "./useLiveChatFeedback";
import { useLiveChatFilters } from "./useLiveChatFilters";
import { useLiveChatList } from "./useLiveChatList";
import { useLiveChatPaging } from "./useLiveChatPaging";
import { useLiveChatSelection } from "./useLiveChatSelection";
import { useLiveChatSession } from "./useLiveChatSession";
import { useLiveChatShared } from "./useLiveChatShared";

/** @param {{ mobile?: boolean }} args */
export function useLiveChatController({ mobile = false }) {
  const s = useLiveChatShared({ mobile });
  useLiveChatList(s);
  useLiveChatFilters(s);
  useLiveChatEffects(s);
  useLiveChatSession(s);
  useLiveChatSelection(s);
  useLiveChatData(s);
  useLiveChatPaging(s);
  useLiveChatActions(s);
  useLiveChatFeedback(s);
  return s;
}
