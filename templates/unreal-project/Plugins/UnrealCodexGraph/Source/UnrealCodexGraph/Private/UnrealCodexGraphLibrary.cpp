#include "UnrealCodexGraphLibrary.h"

#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphNode.h"
#include "EdGraph/EdGraphPin.h"
#include "EdGraphSchema_K2.h"
#include "Engine/Blueprint.h"
#include "K2Node_CallFunction.h"
#include "K2Node_DynamicCast.h"
#include "K2Node_Event.h"
#include "K2Node_ExecutionSequence.h"
#include "K2Node_IfThenElse.h"
#include "K2Node_Knot.h"
#include "K2Node_Self.h"
#include "K2Node_VariableGet.h"
#include "K2Node_VariableSet.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Misc/PackageName.h"
#include "ScopedTransaction.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

namespace UnrealCodexGraph
{
FString ToJson(const TSharedRef<FJsonObject>& Object)
{
    FString Output;
    const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Output);
    FJsonSerializer::Serialize(Object, Writer);
    return Output;
}

FString Error(const FString& Message)
{
    const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("success"), false);
    Result->SetStringField(TEXT("error"), Message);
    return ToJson(Result);
}

UBlueprint* LoadBlueprint(const FString& BlueprintPath, FString& OutError)
{
    FString PackagePath = BlueprintPath;
    FString ObjectName;
    if (BlueprintPath.Split(TEXT("."), &PackagePath, &ObjectName))
    {
        // LoadObject accepts the complete object path below.
    }
    else
    {
        ObjectName = FPackageName::GetLongPackageAssetName(BlueprintPath);
    }

    const FString ObjectPath = BlueprintPath.Contains(TEXT("."))
        ? BlueprintPath
        : FString::Printf(TEXT("%s.%s"), *BlueprintPath, *ObjectName);
    UBlueprint* Blueprint = LoadObject<UBlueprint>(nullptr, *ObjectPath);
    if (!Blueprint)
    {
        OutError = FString::Printf(TEXT("Blueprint not found: %s"), *BlueprintPath);
    }
    return Blueprint;
}

UEdGraph* FindGraph(UBlueprint* Blueprint, const FString& GraphName, FString& OutError)
{
    TArray<UEdGraph*> Graphs;
    Graphs.Append(Blueprint->UbergraphPages);
    Graphs.Append(Blueprint->FunctionGraphs);
    Graphs.Append(Blueprint->MacroGraphs);
    Graphs.Append(Blueprint->DelegateSignatureGraphs);
    for (UEdGraph* Graph : Graphs)
    {
        if (Graph && Graph->GetName().Equals(GraphName, ESearchCase::IgnoreCase))
        {
            return Graph;
        }
    }
    OutError = FString::Printf(TEXT("Graph not found: %s"), *GraphName);
    return nullptr;
}

UClass* LoadOwnerClass(const FString& OwnerClassPath, FString& OutError)
{
    UClass* OwnerClass = LoadObject<UClass>(nullptr, *OwnerClassPath);
    if (!OwnerClass)
    {
        OutError = FString::Printf(TEXT("Class not found: %s"), *OwnerClassPath);
    }
    return OwnerClass;
}

UFunction* FindFunction(UClass* OwnerClass, const FString& FunctionName, FString& OutError)
{
    UFunction* Function = OwnerClass->FindFunctionByName(FName(*FunctionName));
    if (!Function)
    {
        OutError = FString::Printf(
            TEXT("Function not found: %s.%s"),
            *OwnerClass->GetPathName(),
            *FunctionName
        );
    }
    return Function;
}

UEdGraphNode* FindNode(UEdGraph* Graph, const FString& GuidText, FString& OutError)
{
    FGuid Guid;
    if (!FGuid::Parse(GuidText, Guid))
    {
        OutError = FString::Printf(TEXT("Invalid node GUID: %s"), *GuidText);
        return nullptr;
    }
    for (UEdGraphNode* Node : Graph->Nodes)
    {
        if (Node && Node->NodeGuid == Guid)
        {
            return Node;
        }
    }
    OutError = FString::Printf(TEXT("Node not found: %s"), *GuidText);
    return nullptr;
}

FString NormalizePinName(const FString& Name)
{
    FString Result = Name;
    Result.ReplaceInline(TEXT(" "), TEXT(""));
    Result.ReplaceInline(TEXT("_"), TEXT(""));
    return Result.ToLower();
}

UEdGraphPin* FindPin(UEdGraphNode* Node, const FString& PinName, EEdGraphPinDirection Direction, FString& OutError)
{
    const FString Wanted = NormalizePinName(PinName);
    for (UEdGraphPin* Pin : Node->Pins)
    {
        if (Pin && Pin->Direction == Direction && NormalizePinName(Pin->PinName.ToString()) == Wanted)
        {
            return Pin;
        }
    }
    OutError = FString::Printf(
        TEXT("Pin not found on node %s: %s"),
        *Node->NodeGuid.ToString(),
        *PinName
    );
    return nullptr;
}

TSharedRef<FJsonObject> NodeResult(UEdGraphNode* Node)
{
    const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("success"), true);
    Result->SetStringField(TEXT("node_guid"), Node->NodeGuid.ToString());
    Result->SetStringField(TEXT("node_class"), Node->GetClass()->GetPathName());
    Result->SetStringField(TEXT("title"), Node->GetNodeTitle(ENodeTitleType::ListView).ToString());
    return Result;
}

template <typename NodeType>
NodeType* CreateNode(UEdGraph* Graph, const FVector2D& Position)
{
    FGraphNodeCreator<NodeType> Creator(*Graph);
    NodeType* Node = Creator.CreateNode();
    Node->NodePosX = FMath::RoundToInt(Position.X);
    Node->NodePosY = FMath::RoundToInt(Position.Y);
    Creator.Finalize();
    return Node;
}

TSharedPtr<FJsonObject> ParseParameters(const FString& ParametersJson, FString& OutError)
{
    const TSharedPtr<FJsonObject> Parameters = MakeShared<FJsonObject>();
    if (ParametersJson.IsEmpty())
    {
        return Parameters;
    }
    const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(ParametersJson);
    TSharedPtr<FJsonObject> Parsed;
    if (!FJsonSerializer::Deserialize(Reader, Parsed) || !Parsed.IsValid())
    {
        OutError = TEXT("Node parameters must be a valid JSON object");
        return nullptr;
    }
    return Parsed;
}
}

FString UUnrealCodexGraphLibrary::GetCapabilities()
{
    const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("success"), true);
    Result->SetStringField(TEXT("bridge"), TEXT("UnrealCodexGraph"));
    Result->SetStringField(TEXT("bridge_version"), TEXT("0.1.0"));
    Result->SetStringField(TEXT("engine_target"), TEXT("5.8"));
    Result->SetBoolField(TEXT("function_call_nodes"), true);
    Result->SetBoolField(TEXT("event_nodes"), true);
    Result->SetBoolField(TEXT("pin_connections"), true);
    Result->SetBoolField(TEXT("pin_default_values"), true);
    Result->SetBoolField(TEXT("graph_inspection"), true);
    TArray<TSharedPtr<FJsonValue>> NodeKinds;
    for (const TCHAR* Kind : {
        TEXT("function_call"), TEXT("event"), TEXT("branch"), TEXT("sequence"),
        TEXT("reroute"), TEXT("self"), TEXT("variable_get"), TEXT("variable_set"),
        TEXT("dynamic_cast")
    })
    {
        NodeKinds.Add(MakeShared<FJsonValueString>(Kind));
    }
    Result->SetArrayField(TEXT("node_kinds"), NodeKinds);
    return UnrealCodexGraph::ToJson(Result);
}

FString UUnrealCodexGraphLibrary::AddNode(
    const FString& BlueprintPath,
    const FString& GraphName,
    const FString& NodeKind,
    const FString& ParametersJson,
    const FVector2D& Position
)
{
    FString ErrorMessage;
    const TSharedPtr<FJsonObject> Parameters = UnrealCodexGraph::ParseParameters(ParametersJson, ErrorMessage);
    if (!Parameters.IsValid())
    {
        return UnrealCodexGraph::Error(ErrorMessage);
    }

    if (NodeKind.Equals(TEXT("function_call"), ESearchCase::IgnoreCase))
    {
        FString OwnerClass;
        FString Function;
        if (!Parameters->TryGetStringField(TEXT("owner_class"), OwnerClass) ||
            !Parameters->TryGetStringField(TEXT("function"), Function))
        {
            return UnrealCodexGraph::Error(TEXT("function_call requires owner_class and function"));
        }
        return AddFunctionCallNode(BlueprintPath, GraphName, OwnerClass, Function, Position);
    }
    if (NodeKind.Equals(TEXT("event"), ESearchCase::IgnoreCase))
    {
        FString OwnerClass;
        FString Function;
        if (!Parameters->TryGetStringField(TEXT("owner_class"), OwnerClass) ||
            !Parameters->TryGetStringField(TEXT("function"), Function))
        {
            return UnrealCodexGraph::Error(TEXT("event requires owner_class and function"));
        }
        return AddEventNode(BlueprintPath, GraphName, OwnerClass, Function, Position);
    }

    UBlueprint* Blueprint = UnrealCodexGraph::LoadBlueprint(BlueprintPath, ErrorMessage);
    UEdGraph* Graph = Blueprint ? UnrealCodexGraph::FindGraph(Blueprint, GraphName, ErrorMessage) : nullptr;
    if (!Graph)
    {
        return UnrealCodexGraph::Error(ErrorMessage);
    }

    const FScopedTransaction Transaction(NSLOCTEXT("UnrealCodexGraph", "AddNode", "Add Blueprint graph node"));
    Blueprint->Modify();
    Graph->Modify();
    UEdGraphNode* Node = nullptr;

    if (NodeKind.Equals(TEXT("branch"), ESearchCase::IgnoreCase))
    {
        Node = UnrealCodexGraph::CreateNode<UK2Node_IfThenElse>(Graph, Position);
    }
    else if (NodeKind.Equals(TEXT("sequence"), ESearchCase::IgnoreCase))
    {
        Node = UnrealCodexGraph::CreateNode<UK2Node_ExecutionSequence>(Graph, Position);
    }
    else if (NodeKind.Equals(TEXT("reroute"), ESearchCase::IgnoreCase))
    {
        Node = UnrealCodexGraph::CreateNode<UK2Node_Knot>(Graph, Position);
    }
    else if (NodeKind.Equals(TEXT("self"), ESearchCase::IgnoreCase))
    {
        Node = UnrealCodexGraph::CreateNode<UK2Node_Self>(Graph, Position);
    }
    else if (NodeKind.Equals(TEXT("variable_get"), ESearchCase::IgnoreCase) ||
             NodeKind.Equals(TEXT("variable_set"), ESearchCase::IgnoreCase))
    {
        FString VariableName;
        if (!Parameters->TryGetStringField(TEXT("variable_name"), VariableName) || VariableName.IsEmpty())
        {
            return UnrealCodexGraph::Error(TEXT("Variable nodes require variable_name"));
        }
        if (NodeKind.Equals(TEXT("variable_get"), ESearchCase::IgnoreCase))
        {
            FGraphNodeCreator<UK2Node_VariableGet> Creator(*Graph);
            UK2Node_VariableGet* VariableNode = Creator.CreateNode();
            VariableNode->VariableReference.SetSelfMember(FName(*VariableName));
            VariableNode->NodePosX = FMath::RoundToInt(Position.X);
            VariableNode->NodePosY = FMath::RoundToInt(Position.Y);
            Creator.Finalize();
            Node = VariableNode;
        }
        else
        {
            FGraphNodeCreator<UK2Node_VariableSet> Creator(*Graph);
            UK2Node_VariableSet* VariableNode = Creator.CreateNode();
            VariableNode->VariableReference.SetSelfMember(FName(*VariableName));
            VariableNode->NodePosX = FMath::RoundToInt(Position.X);
            VariableNode->NodePosY = FMath::RoundToInt(Position.Y);
            Creator.Finalize();
            Node = VariableNode;
        }
    }
    else if (NodeKind.Equals(TEXT("dynamic_cast"), ESearchCase::IgnoreCase))
    {
        FString TargetClassPath;
        if (!Parameters->TryGetStringField(TEXT("target_class"), TargetClassPath))
        {
            return UnrealCodexGraph::Error(TEXT("dynamic_cast requires target_class"));
        }
        UClass* TargetClass = UnrealCodexGraph::LoadOwnerClass(TargetClassPath, ErrorMessage);
        if (!TargetClass)
        {
            return UnrealCodexGraph::Error(ErrorMessage);
        }
        FGraphNodeCreator<UK2Node_DynamicCast> Creator(*Graph);
        UK2Node_DynamicCast* CastNode = Creator.CreateNode();
        CastNode->TargetType = TargetClass;
        CastNode->NodePosX = FMath::RoundToInt(Position.X);
        CastNode->NodePosY = FMath::RoundToInt(Position.Y);
        Creator.Finalize();
        Node = CastNode;
    }
    else
    {
        return UnrealCodexGraph::Error(FString::Printf(TEXT("Unsupported node kind: %s"), *NodeKind));
    }

    if (!Node)
    {
        return UnrealCodexGraph::Error(TEXT("Unreal could not create the requested node"));
    }
    FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);
    return UnrealCodexGraph::ToJson(UnrealCodexGraph::NodeResult(Node));
}

FString UUnrealCodexGraphLibrary::InspectGraph(const FString& BlueprintPath, const FString& GraphName)
{
    FString ErrorMessage;
    UBlueprint* Blueprint = UnrealCodexGraph::LoadBlueprint(BlueprintPath, ErrorMessage);
    if (!Blueprint)
    {
        return UnrealCodexGraph::Error(ErrorMessage);
    }
    UEdGraph* Graph = UnrealCodexGraph::FindGraph(Blueprint, GraphName, ErrorMessage);
    if (!Graph)
    {
        return UnrealCodexGraph::Error(ErrorMessage);
    }

    TArray<TSharedPtr<FJsonValue>> Nodes;
    for (UEdGraphNode* Node : Graph->Nodes)
    {
        if (!Node)
        {
            continue;
        }
        const TSharedRef<FJsonObject> NodeJson = MakeShared<FJsonObject>();
        NodeJson->SetStringField(TEXT("guid"), Node->NodeGuid.ToString());
        NodeJson->SetStringField(TEXT("class"), Node->GetClass()->GetPathName());
        NodeJson->SetStringField(TEXT("title"), Node->GetNodeTitle(ENodeTitleType::ListView).ToString());
        NodeJson->SetNumberField(TEXT("x"), Node->NodePosX);
        NodeJson->SetNumberField(TEXT("y"), Node->NodePosY);
        TArray<TSharedPtr<FJsonValue>> Pins;
        for (UEdGraphPin* Pin : Node->Pins)
        {
            if (!Pin)
            {
                continue;
            }
            const TSharedRef<FJsonObject> PinJson = MakeShared<FJsonObject>();
            PinJson->SetStringField(TEXT("name"), Pin->PinName.ToString());
            PinJson->SetStringField(
                TEXT("direction"),
                Pin->Direction == EGPD_Input ? TEXT("input") : TEXT("output")
            );
            PinJson->SetStringField(TEXT("category"), Pin->PinType.PinCategory.ToString());
            PinJson->SetStringField(TEXT("subcategory"), Pin->PinType.PinSubCategory.ToString());
            PinJson->SetStringField(TEXT("default_value"), Pin->DefaultValue);
            TArray<TSharedPtr<FJsonValue>> Linked;
            for (UEdGraphPin* LinkedPin : Pin->LinkedTo)
            {
                if (LinkedPin && LinkedPin->GetOwningNode())
                {
                    Linked.Add(MakeShared<FJsonValueString>(
                        LinkedPin->GetOwningNode()->NodeGuid.ToString() + TEXT(":") + LinkedPin->PinName.ToString()
                    ));
                }
            }
            PinJson->SetArrayField(TEXT("linked_to"), Linked);
            Pins.Add(MakeShared<FJsonValueObject>(PinJson));
        }
        NodeJson->SetArrayField(TEXT("pins"), Pins);
        Nodes.Add(MakeShared<FJsonValueObject>(NodeJson));
    }

    const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("success"), true);
    Result->SetStringField(TEXT("blueprint"), BlueprintPath);
    Result->SetStringField(TEXT("graph"), GraphName);
    Result->SetArrayField(TEXT("nodes"), Nodes);
    return UnrealCodexGraph::ToJson(Result);
}

FString UUnrealCodexGraphLibrary::ListGraphs(const FString& BlueprintPath)
{
    FString ErrorMessage;
    UBlueprint* Blueprint = UnrealCodexGraph::LoadBlueprint(BlueprintPath, ErrorMessage);
    if (!Blueprint)
    {
        return UnrealCodexGraph::Error(ErrorMessage);
    }

    TArray<TSharedPtr<FJsonValue>> Graphs;
    const auto AppendGraphs = [&Graphs](const TArray<TObjectPtr<UEdGraph>>& Source, const FString& Kind)
    {
        for (const UEdGraph* Graph : Source)
        {
            if (!Graph)
            {
                continue;
            }
            const TSharedRef<FJsonObject> Item = MakeShared<FJsonObject>();
            Item->SetStringField(TEXT("name"), Graph->GetName());
            Item->SetStringField(TEXT("kind"), Kind);
            Graphs.Add(MakeShared<FJsonValueObject>(Item));
        }
    };
    AppendGraphs(Blueprint->UbergraphPages, TEXT("event"));
    AppendGraphs(Blueprint->FunctionGraphs, TEXT("function"));
    AppendGraphs(Blueprint->MacroGraphs, TEXT("macro"));
    AppendGraphs(Blueprint->DelegateSignatureGraphs, TEXT("delegate"));

    const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("success"), true);
    Result->SetStringField(TEXT("blueprint"), BlueprintPath);
    Result->SetStringField(
        TEXT("parent_class"),
        Blueprint->ParentClass ? Blueprint->ParentClass->GetPathName() : FString()
    );
    Result->SetStringField(
        TEXT("generated_class"),
        Blueprint->GeneratedClass ? Blueprint->GeneratedClass->GetPathName() : FString()
    );
    Result->SetArrayField(TEXT("graphs"), Graphs);
    return UnrealCodexGraph::ToJson(Result);
}

FString UUnrealCodexGraphLibrary::AddFunctionCallNode(
    const FString& BlueprintPath,
    const FString& GraphName,
    const FString& OwnerClassPath,
    const FString& FunctionName,
    const FVector2D& Position
)
{
    FString ErrorMessage;
    UBlueprint* Blueprint = UnrealCodexGraph::LoadBlueprint(BlueprintPath, ErrorMessage);
    UEdGraph* Graph = Blueprint ? UnrealCodexGraph::FindGraph(Blueprint, GraphName, ErrorMessage) : nullptr;
    UClass* OwnerClass = Graph ? UnrealCodexGraph::LoadOwnerClass(OwnerClassPath, ErrorMessage) : nullptr;
    UFunction* Function = OwnerClass ? UnrealCodexGraph::FindFunction(OwnerClass, FunctionName, ErrorMessage) : nullptr;
    if (!Function)
    {
        return UnrealCodexGraph::Error(ErrorMessage);
    }

    const FScopedTransaction Transaction(NSLOCTEXT("UnrealCodexGraph", "AddFunctionCallNode", "Add Blueprint function call node"));
    Blueprint->Modify();
    Graph->Modify();
    FGraphNodeCreator<UK2Node_CallFunction> Creator(*Graph);
    UK2Node_CallFunction* Node = Creator.CreateNode();
    Node->SetFromFunction(Function);
    Node->NodePosX = FMath::RoundToInt(Position.X);
    Node->NodePosY = FMath::RoundToInt(Position.Y);
    Creator.Finalize();
    FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);
    return UnrealCodexGraph::ToJson(UnrealCodexGraph::NodeResult(Node));
}

FString UUnrealCodexGraphLibrary::AddEventNode(
    const FString& BlueprintPath,
    const FString& GraphName,
    const FString& OwnerClassPath,
    const FString& FunctionName,
    const FVector2D& Position
)
{
    FString ErrorMessage;
    UBlueprint* Blueprint = UnrealCodexGraph::LoadBlueprint(BlueprintPath, ErrorMessage);
    UEdGraph* Graph = Blueprint ? UnrealCodexGraph::FindGraph(Blueprint, GraphName, ErrorMessage) : nullptr;
    UClass* OwnerClass = Graph ? UnrealCodexGraph::LoadOwnerClass(OwnerClassPath, ErrorMessage) : nullptr;
    UFunction* Function = OwnerClass ? UnrealCodexGraph::FindFunction(OwnerClass, FunctionName, ErrorMessage) : nullptr;
    if (!Function)
    {
        return UnrealCodexGraph::Error(ErrorMessage);
    }

    for (UEdGraphNode* ExistingNode : Graph->Nodes)
    {
        UK2Node_Event* ExistingEvent = Cast<UK2Node_Event>(ExistingNode);
        if (ExistingEvent && ExistingEvent->EventReference.GetMemberName() == Function->GetFName())
        {
            const TSharedRef<FJsonObject> Result = UnrealCodexGraph::NodeResult(ExistingEvent);
            Result->SetBoolField(TEXT("existing"), true);
            return UnrealCodexGraph::ToJson(Result);
        }
    }

    const FScopedTransaction Transaction(NSLOCTEXT("UnrealCodexGraph", "AddEventNode", "Add Blueprint event node"));
    Blueprint->Modify();
    Graph->Modify();
    FGraphNodeCreator<UK2Node_Event> Creator(*Graph);
    UK2Node_Event* Node = Creator.CreateNode();
    Node->EventReference.SetExternalMember(Function->GetFName(), OwnerClass);
    Node->bOverrideFunction = true;
    Node->NodePosX = FMath::RoundToInt(Position.X);
    Node->NodePosY = FMath::RoundToInt(Position.Y);
    Creator.Finalize();
    FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);
    return UnrealCodexGraph::ToJson(UnrealCodexGraph::NodeResult(Node));
}

FString UUnrealCodexGraphLibrary::ConnectPins(
    const FString& BlueprintPath,
    const FString& GraphName,
    const FString& FromNodeGuid,
    const FString& FromPinName,
    const FString& ToNodeGuid,
    const FString& ToPinName
)
{
    FString ErrorMessage;
    UBlueprint* Blueprint = UnrealCodexGraph::LoadBlueprint(BlueprintPath, ErrorMessage);
    UEdGraph* Graph = Blueprint ? UnrealCodexGraph::FindGraph(Blueprint, GraphName, ErrorMessage) : nullptr;
    UEdGraphNode* FromNode = Graph ? UnrealCodexGraph::FindNode(Graph, FromNodeGuid, ErrorMessage) : nullptr;
    UEdGraphNode* ToNode = FromNode ? UnrealCodexGraph::FindNode(Graph, ToNodeGuid, ErrorMessage) : nullptr;
    UEdGraphPin* FromPin = ToNode ? UnrealCodexGraph::FindPin(FromNode, FromPinName, EGPD_Output, ErrorMessage) : nullptr;
    UEdGraphPin* ToPin = FromPin ? UnrealCodexGraph::FindPin(ToNode, ToPinName, EGPD_Input, ErrorMessage) : nullptr;
    if (!ToPin)
    {
        return UnrealCodexGraph::Error(ErrorMessage);
    }

    const UEdGraphSchema_K2* Schema = GetDefault<UEdGraphSchema_K2>();
    const FPinConnectionResponse Response = Schema->CanCreateConnection(FromPin, ToPin);
    if (Response.Response == CONNECT_RESPONSE_DISALLOW)
    {
        return UnrealCodexGraph::Error(Response.Message.ToString());
    }
    const FScopedTransaction Transaction(NSLOCTEXT("UnrealCodexGraph", "ConnectPins", "Connect Blueprint pins"));
    Blueprint->Modify();
    Graph->Modify();
    if (!Schema->TryCreateConnection(FromPin, ToPin))
    {
        return UnrealCodexGraph::Error(TEXT("Unreal rejected the pin connection"));
    }
    FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);
    const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("success"), true);
    Result->SetStringField(TEXT("from"), FromNodeGuid + TEXT(":") + FromPinName);
    Result->SetStringField(TEXT("to"), ToNodeGuid + TEXT(":") + ToPinName);
    return UnrealCodexGraph::ToJson(Result);
}

FString UUnrealCodexGraphLibrary::SetPinDefaultValue(
    const FString& BlueprintPath,
    const FString& GraphName,
    const FString& NodeGuid,
    const FString& PinName,
    const FString& Value
)
{
    FString ErrorMessage;
    UBlueprint* Blueprint = UnrealCodexGraph::LoadBlueprint(BlueprintPath, ErrorMessage);
    UEdGraph* Graph = Blueprint ? UnrealCodexGraph::FindGraph(Blueprint, GraphName, ErrorMessage) : nullptr;
    UEdGraphNode* Node = Graph ? UnrealCodexGraph::FindNode(Graph, NodeGuid, ErrorMessage) : nullptr;
    UEdGraphPin* Pin = Node ? UnrealCodexGraph::FindPin(Node, PinName, EGPD_Input, ErrorMessage) : nullptr;
    if (!Pin)
    {
        return UnrealCodexGraph::Error(ErrorMessage);
    }

    const UEdGraphSchema_K2* Schema = GetDefault<UEdGraphSchema_K2>();
    const FScopedTransaction Transaction(NSLOCTEXT("UnrealCodexGraph", "SetPinDefaultValue", "Set Blueprint pin default value"));
    Blueprint->Modify();
    Graph->Modify();
    Schema->TrySetDefaultValue(*Pin, Value);
    FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);
    const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("success"), true);
    Result->SetStringField(TEXT("node_guid"), NodeGuid);
    Result->SetStringField(TEXT("pin"), PinName);
    Result->SetStringField(TEXT("value"), Value);
    return UnrealCodexGraph::ToJson(Result);
}
