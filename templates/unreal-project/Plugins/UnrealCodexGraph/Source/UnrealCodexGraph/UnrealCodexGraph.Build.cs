using UnrealBuildTool;

public class UnrealCodexGraph : ModuleRules
{
    public UnrealCodexGraph(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicDependencyModuleNames.AddRange(
            new[]
            {
                "Core",
                "CoreUObject",
                "Engine"
            }
        );

        PrivateDependencyModuleNames.AddRange(
            new[]
            {
                "BlueprintGraph",
                "Json",
                "KismetCompiler",
                "UnrealEd"
            }
        );
    }
}
