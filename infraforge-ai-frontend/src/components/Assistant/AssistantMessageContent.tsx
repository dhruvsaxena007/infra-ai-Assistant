import React, { memo } from "react";
import AssistantMarkdown from "./AssistantMarkdown";
import ConstructionCraneTextBuilder from "./ConstructionCraneTextBuilder";
import ProgressiveResponseText from "./ProgressiveResponseText";

interface Props {
  text: string;
  displayedText?: string;
  messageId: string;
  isGenerating: boolean;
  usePlainText: boolean;
  indicatorFading?: boolean;
}

function AssistantMessageContent({
  text,
  displayedText,
  messageId,
  isGenerating,
  usePlainText,
  indicatorFading = false,
}: Props) {
  const visibleText = isGenerating ? (displayedText ?? "") : text;

  if (usePlainText || isGenerating) {
    return (
      <span className="progressive-response whitespace-pre-wrap break-words">
        <ProgressiveResponseText text={visibleText} isGenerating={isGenerating} />
        {isGenerating && (
          <ConstructionCraneTextBuilder
            key={messageId}
            messageId={messageId}
            fading={indicatorFading}
          />
        )}
      </span>
    );
  }

  return <AssistantMarkdown content={text} />;
}

export default memo(AssistantMessageContent);
