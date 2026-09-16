#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "UnrealCodexGraphLibrary.generated.h"

UCLASS()
class UNREALCODEXGRAPH_API UUnrealCodexGraphLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    UFUNCTION(BlueprintCallable, Category = "Unreal Codex|Blueprint Graph")
    static FString GetCapabilities();

    UFUNCTION(BlueprintCallable, Category = "Unreal Codex|Blueprint Graph")
    static FString InspectGraph(const FString& BlueprintPath, const FString& GraphName);

    UFUNCTION(BlueprintCallable, Category = "Unreal Codex|Blueprint Graph")
    static FString ListGraphs(const FString& BlueprintPath);

    UFUNCTION(BlueprintCallable, Category = "Unreal Codex|Blueprint Graph")
    static FString AddNode(
        const FString& BlueprintPath,
        const FString& GraphName,
        const FString& NodeKind,
        const FString& ParametersJson,
        const FVector2D& Position
    );

    UFUNCTION(BlueprintCallable, Category = "Unreal Codex|Blueprint Graph")
    static FString AddFunctionCallNode(
        const FString& BlueprintPath,
        const FString& GraphName,
        const FString& OwnerClassPath,
        const FString& FunctionName,
        const FVector2D& Position
    );

    UFUNCTION(BlueprintCallable, Category = "Unreal Codex|Blueprint Graph")
    static FString AddEventNode(
        const FString& BlueprintPath,
        const FString& GraphName,
        const FString& OwnerClassPath,
        const FString& FunctionName,
        const FVector2D& Position
    );

    UFUNCTION(BlueprintCallable, Category = "Unreal Codex|Blueprint Graph")
    static FString ConnectPins(
        const FString& BlueprintPath,
        const FString& GraphName,
        const FString& FromNodeGuid,
        const FString& FromPinName,
        const FString& ToNodeGuid,
        const FString& ToPinName
    );

    UFUNCTION(BlueprintCallable, Category = "Unreal Codex|Blueprint Graph")
    static FString SetPinDefaultValue(
        const FString& BlueprintPath,
        const FString& GraphName,
        const FString& NodeGuid,
        const FString& PinName,
        const FString& Value
    );
};
