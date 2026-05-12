class PipelineConfig:
        #     config = PipelineConfig(
        #     vlm_model=model,
        #     dpi=300,
        #     min_question_gap=18,
        #     layout_model="doclayout-yolo"                    
        # )
    def __init__(self, vlm_model, dpi=300, min_question_gap=18, layout_model="doclayout-yolo"):
        self.vlm_model = vlm_model
        self.dpi = dpi
        self.min_question_gap = min_question_gap
        self.layout_model = layout_model
    